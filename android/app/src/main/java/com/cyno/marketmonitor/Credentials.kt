package com.cyno.marketmonitor

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import org.json.JSONObject

class Credentials(private val context:Context) {
    private val path=File(context.filesDir,"credentials.enc")
    private fun key():SecretKey {
        val store=KeyStore.getInstance("AndroidKeyStore").apply{load(null)}
        return (store.getKey("market-monitor",null) as? SecretKey)?:KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder("market-monitor",KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build())
        }.generateKey()
    }
    fun import(value:JSONObject) {
        val account=value.getJSONObject("longbridge").objects("accounts").single{it.getString("id")=="account_2"}
        listOf("app_key","app_secret","access_token").forEach{require(account.getString(it).isNotBlank()){"Account 2 credentials are incomplete"}}
        val trimmed=json("longbridge" to json("accounts" to array(listOf(account))),"massive" to json("api_key" to value.getJSONObject("massive").getString("api_key")))
        val cipher=Cipher.getInstance("AES/GCM/NoPadding").apply{init(Cipher.ENCRYPT_MODE,key())}
        path.writeBytes(cipher.iv+cipher.doFinal(trimmed.toString().toByteArray()))
    }
    fun load():JSONObject? {
        val pending=File(context.filesDir,"provision.json")
        if(pending.exists()) {try{import(JSONObject(pending.readText()))}finally{pending.delete()}}
        if(!path.exists())try{context.assets.open("provision.json").bufferedReader().use{import(JSONObject(it.readText()))}}catch(_:java.io.FileNotFoundException){}
        if(!path.exists())return null
        val bytes=path.readBytes();val cipher=Cipher.getInstance("AES/GCM/NoPadding").apply{init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,bytes.copyOfRange(0,12)))}
        return JSONObject(String(cipher.doFinal(bytes.copyOfRange(12,bytes.size))))
    }
}
