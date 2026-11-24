package com.cyno.marketmonitor

import kotlinx.coroutines.*
import okhttp3.*
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class SourceHttp(private val interval:Long=0) {
    val client=OkHttpClient.Builder().connectTimeout(15,TimeUnit.SECONDS).readTimeout(30,TimeUnit.SECONDS).callTimeout(35,TimeUnit.SECONDS).build()
    private var started=0L
    suspend fun text(url:String,headers:Map<String,String> = emptyMap()):String {
        var error="Network request failed"
        for(attempt in 0..3) {
            currentCoroutineContext().ensureActive()
            if(attempt>0)delay(listOf(2000L,5000L,10000L)[attempt-1])
            delay((started+interval-System.currentTimeMillis()).coerceAtLeast(0));started=System.currentTimeMillis()
            try {
                return withContext(Dispatchers.IO) {
                    val request=Request.Builder().url(url).apply{headers.forEach{(k,v)->header(k,v)}}.build()
                    client.newCall(request).execute().use {response->
                        if(!response.isSuccessful)throw IOException("HTTP ${response.code}")
                        response.body?.string()?:throw IOException("Empty response")
                    }
                }
            } catch(e:IOException) {error=if(e.message?.startsWith("HTTP ")==true)e.message!! else "Network unavailable or timed out"}
        }
        throw IOException(error)
    }
    suspend fun json(url:String,headers:Map<String,String> = emptyMap())=JSONObject(text(url,headers))
}

fun canonical(value:Any?):String = when(value) {
    is JSONObject -> value.keys().asSequence().toList().sorted().joinToString(",","{","}"){JSONObject.quote(it)+":"+canonical(value.get(it))}
    is org.json.JSONArray -> (0 until value.length()).joinToString(",","[","]"){canonical(value.get(it))}
    is String -> JSONObject.quote(value)
    null, JSONObject.NULL -> "null"
    else -> value.toString()
}
fun digest(value:String)=java.security.MessageDigest.getInstance("SHA-256").digest(value.toByteArray()).joinToString(""){"%02x".format(it)}
