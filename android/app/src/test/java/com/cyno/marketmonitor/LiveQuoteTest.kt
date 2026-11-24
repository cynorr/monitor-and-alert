package com.cyno.marketmonitor

import kotlinx.coroutines.*
import org.json.JSONObject
import org.junit.Test
import org.junit.Assert.*
import java.io.File
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicReference

class LiveQuoteTest {
    @Test fun accountTwoReadOnlyQuoteCheck()=runBlocking {
        val path=System.getenv("ANDROID_QUOTE_CREDENTIALS")
        org.junit.Assume.assumeTrue("Explicit bounded live check only",!path.isNullOrEmpty())
        val account=JSONObject(File(path!!).readText()).getJSONObject("longbridge").objects("accounts").single{it.getString("id")=="account_2"}
        val received=ConcurrentHashMap<String,Quote>();val status=AtomicReference("")
        val symbols=setOf("AAPL.US","NVDA.US")
        val quotes=LongbridgeQuotes(account,{symbol,quote->received[symbol]=quote},{status.set(it)})
        try {
            quotes.start(symbols)
            withTimeout(40000){while(!received.keys.containsAll(symbols)){delay(100)}}
            assertEquals(symbols,received.keys);assertTrue(received.values.all{it.price>0&&it.timestamp>0})
            println("Bounded live check passed: account_2; AAPL/NVDA; no candle or trading calls")
        }catch(e:TimeoutCancellationException){fail("Quote timeout: ${status.get()}")}
        finally{quotes.close()}
    }
}
