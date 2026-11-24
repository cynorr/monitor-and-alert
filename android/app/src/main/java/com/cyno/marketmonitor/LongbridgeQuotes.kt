package com.cyno.marketmonitor

import com.google.protobuf.CodedInputStream
import com.google.protobuf.CodedOutputStream
import kotlinx.coroutines.*
import okhttp3.*
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.nio.ByteBuffer
import java.security.MessageDigest
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.zip.GZIPInputStream
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/** Fields used from upstream control/control.proto and quote/api.proto; unknown fields are skipped. */
object QuoteWire {
    fun message(block:CodedOutputStream.()->Unit):ByteArray {val stream=ByteArrayOutputStream();val output=CodedOutputStream.newInstance(stream);output.block();output.flush();return stream.toByteArray()}
    fun fields(bytes:ByteArray):Map<Int,List<Any>> {
        val input=CodedInputStream.newInstance(bytes);val result=mutableMapOf<Int,MutableList<Any>>()
        while(!input.isAtEnd){val tag=input.readTag();if(tag==0)break;val value:Any=when(tag and 7){0->input.readInt64();2->input.readByteArray();else->{input.skipField(tag);continue}};result.getOrPut(tag ushr 3){mutableListOf()}.add(value)}
        return result
    }
    fun Map<Int,List<Any>>.text(key:Int)=((get(key)?.firstOrNull())as?ByteArray)?.toString(Charsets.UTF_8)?:""
    fun Map<Int,List<Any>>.integer(key:Int)=(get(key)?.firstOrNull()as?Long)?:0L
    data class Packet(val type:Int,val command:Int,val id:Int,val status:Int,val body:ByteArray)
    fun request(command:Int,id:Int,body:ByteArray):ByteArray=ByteBuffer.allocate(11+body.size).apply{put(1);put(command.toByte());putInt(id);putShort(15000);put((body.size ushr 16).toByte());put((body.size ushr 8).toByte());put(body.size.toByte());put(body)}.array()
    fun packets(bytes:ByteArray):List<Packet> {
        val input=ByteBuffer.wrap(bytes);val result=mutableListOf<Packet>()
        while(input.hasRemaining()) {
            val flags=input.get().toInt()and 255;val type=flags and 15;val command=input.get().toInt()and 255
            require(type in 1..3){"Unknown quote packet"};val id=if(type!=3)input.int else 0
            val status=if(type==2)input.get().toInt()and 255 else 0;if(type==1)input.short
            val size=((input.get().toInt()and 255)shl 16)or((input.get().toInt()and 255)shl 8)or(input.get().toInt()and 255)
            require(size<=input.remaining()){"Truncated quote packet"};var body=ByteArray(size);input.get(body)
            if(flags and 16!=0){require(input.remaining()>=24);input.position(input.position()+24)}
            if(flags and 32!=0)body=GZIPInputStream(body.inputStream()).use{it.readBytes()}
            result.add(Packet(type,command,id,status,body))
        }
        return result
    }
    fun signature(key:String,secret:String,token:String,timestamp:String,path:String):String {
        val plain="GET|$path||authorization:$token\nx-api-key:$key\nx-timestamp:$timestamp\n|authorization;x-api-key;x-timestamp|"
        val hash=MessageDigest.getInstance("SHA-1").digest(plain.toByteArray()).joinToString(""){"%02x".format(it)}
        val mac=Mac.getInstance("HmacSHA256").apply{init(SecretKeySpec(secret.toByteArray(),"HmacSHA256"))}
        return mac.doFinal("HMAC-SHA256|$hash".toByteArray()).joinToString(""){"%02x".format(it)}
    }
}

class LongbridgeQuotes(private val account:JSONObject,private val onQuote:(String,Quote)->Unit,private val onStatus:(String)->Unit) {
    private val scope=CoroutineScope(SupervisorJob()+Dispatchers.IO)
    private val http=SourceHttp()
    private val client=http.client.newBuilder().pingInterval(15,TimeUnit.SECONDS).readTimeout(0,TimeUnit.MILLISECONDS).build()
    private val pending=ConcurrentHashMap<Int,CompletableDeferred<ByteArray>>()
    private val counter=AtomicInteger(1)
    @Volatile private var socket:WebSocket?=null
    @Volatile private var symbols=emptySet<String>()
    @Volatile private var ready=false
    private var runner:Job?=null
    fun start(values:Set<String>) {symbols=values;if(runner!=null)return;runner=scope.launch{var attempt=0;while(isActive){try{connect();attempt=0}catch(e:CancellationException){throw e}catch(e:Exception){onStatus(if(e is IllegalArgumentException)e.message?:"Quote error" else "Quote disconnected · reconnecting")};ready=false;socket?.cancel();socket=null;pending.values.forEach{it.cancel()};pending.clear();delay(listOf(1000L,2000L,5000L,10000L,30000L)[(attempt++).coerceAtMost(4)])}}}
    fun update(values:Set<String>) {if(values==symbols)return;val old=symbols;symbols=values;if(ready)scope.launch{try{subscribe(values-old);unsubscribe(old-values)}catch(e:CancellationException){throw e}catch(e:Exception){socket?.cancel()}}}
    fun close(){ready=false;scope.cancel();socket?.close(1000,"Background");socket=null;pending.values.forEach{it.cancel()};pending.clear();onStatus("Quote paused")}
    private suspend fun request(command:Int,body:ByteArray):ByteArray {
        val id=counter.getAndIncrement();val reply=CompletableDeferred<ByteArray>();pending[id]=reply
        try{check(socket?.send(QuoteWire.request(command,id,body).toByteString())==true){"Quote socket unavailable"};return withTimeout(15000){reply.await()}}finally{pending.remove(id)}
    }
    private suspend fun connect() {
        require(account.getString("id")=="account_2"){"Android uses account 2 only"};onStatus("Quote connecting · account 2")
        val path="/v2/socket/token";val stamp=(System.currentTimeMillis()/1000).toString()
        val key=account.getString("app_key").trim().removePrefix("Bearer ");val secret=account.getString("app_secret").trim();val token=account.getString("access_token").trim().removePrefix("Bearer ")
        val signature=QuoteWire.signature(key,secret,token,stamp,path)
        val response=http.json("https://openapi.longbridge.cn$path",mapOf("Authorization" to token,"X-Api-Key" to key,"X-Timestamp" to stamp,"X-Api-Signature" to "HMAC-SHA256 SignedHeaders=authorization;x-api-key;x-timestamp, Signature=$signature","X-DC-Region" to if(listOf(key,secret,token).any{it.startsWith("us_")})"us"else"ap"))
        require(response.optInt("code")==0){"Longbridge authentication error ${response.optInt("code")}"};val otp=response.getJSONObject("data").getString("otp")
        val opened=CompletableDeferred<Unit>();val ended=CompletableDeferred<Unit>()
        val listener=object:WebSocketListener(){
            override fun onOpen(webSocket:WebSocket,response:Response){socket=webSocket;opened.complete(Unit)}
            override fun onMessage(webSocket:WebSocket,bytes:okio.ByteString){
                try{QuoteWire.packets(bytes.toByteArray()).forEach{packet->
                    if(packet.type==2){val reply=pending[packet.id];if(packet.status==0)reply?.complete(packet.body)else reply?.completeExceptionally(IllegalArgumentException("Longbridge command ${packet.command} failed · ${packet.status}"))}
                    else if(packet.type==3&&packet.command==101)push(packet.body)
                    else if(packet.type==3&&packet.command==0)ended.completeExceptionally(IOException("Quote closed"))
                }}catch(e:Exception){ended.completeExceptionally(e);webSocket.cancel()}
            }
            override fun onFailure(webSocket:WebSocket,t:Throwable,response:Response?){opened.completeExceptionally(IOException("Quote connection failed"));ended.completeExceptionally(IOException("Quote connection failed"))}
            override fun onClosed(webSocket:WebSocket,code:Int,reason:String){ended.complete(Unit)}
        }
        socket=client.newWebSocket(Request.Builder().url("wss://openapi-quote.longbridge.cn/v2?version=1&codec=1&platform=9").build(),listener)
        withTimeout(20000){opened.await()}
        val metadata=QuoteWire.message{writeString(1,"need_over_night_quote");writeString(2,"true")}
        request(2,QuoteWire.message{writeString(1,otp);writeByteArray(2,metadata)})
        request(4,QuoteWire.message{writeString(1,"en")})
        val initial=symbols;subscribe(initial);ready=true
        if(symbols!=initial){subscribe(symbols-initial);unsubscribe(initial-symbols)}
        onStatus("Quote connected · account 2");ended.await()
    }
    private suspend fun subscribe(values:Set<String>) {
        require(symbols.size<=500){"Quote scope exceeds 500 symbols"}
        values.sorted().chunked(100).forEach{batch->
            request(6,QuoteWire.message{batch.forEach{writeString(1,it)};writeEnum(2,1);writeBool(3,true)})
            val values=QuoteWire.fields(request(11,QuoteWire.message{batch.forEach{writeString(1,it)}}))
            values[1]?.forEach{snapshot(it as ByteArray)};delay(250)
        }
    }
    private suspend fun unsubscribe(values:Set<String>){values.sorted().chunked(100).forEach{batch->request(7,QuoteWire.message{batch.forEach{writeString(1,it)};writeEnum(2,1)})}}
    private fun push(body:ByteArray){with(QuoteWire){val data=fields(body);publish(data.text(1),data.text(3),data.integer(7),listOf("regular","pre","post","overnight").getOrElse(data.integer(11).toInt()){"regular"})}}
    private fun snapshot(body:ByteArray){with(QuoteWire){val data=fields(body);val symbol=data.text(1);val previous=data.text(3).toDoubleOrNull();publish(symbol,data.text(2),data.integer(7),"regular",previous);listOf(11 to "pre",12 to "post",13 to "overnight").forEach{(field,session)->(data[field]?.firstOrNull()as?ByteArray)?.let{val quote=fields(it);publish(symbol,quote.text(1),quote.integer(2),session,previous)}}}}
    private fun publish(symbol:String,raw:String,time:Long,session:String,previous:Double?=null){val price=raw.toDoubleOrNull();if(symbol in symbols&&price!=null&&price.isFinite()&&price>0&&time>0)onQuote(symbol,Quote(price,time,session,previous))}
}
