package com.cyno.marketmonitor

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.Assert.*
import org.json.JSONObject
import java.time.LocalDate

@RunWith(AndroidJUnit4::class)
class DeviceScanTest {
    @Test fun fullMarketScanMatchesImportedPythonReference(){
        val instrumentation=InstrumentationRegistry.getInstrumentation()
        val store=LocalStore(instrumentation.targetContext);store.initialize{}
        val reference=JSONObject(instrumentation.context.assets.open("scan-reference.json").bufferedReader().use{it.readText()})
        val day=reference.getString("date");val expected=reference.objects("rows").associateBy{it.getString("symbol")}
        val actual=mutableListOf<JSONObject>()
        store.openDaily().use{db->
            db.rawQuery("SELECT symbol FROM bars WHERE timeframe='1d' AND ts=? ORDER BY symbol",arrayOf(store.calendar.stamp(LocalDate.parse(day)).toString())).use{c->while(c.moveToNext()){val symbol=c.getString(0);actual.add(ScanMath.metrics(store.screeningBars(symbol,day,db)))}}
        }
        ScanMath.rank(actual,store.config,store.read("symbol-directory.json").getJSONObject("symbols"))
        assertEquals(expected.keys,actual.map{it.getString("symbol")}.toSet())
        actual.forEach{row->val symbol=row.getString("symbol");val original=expected.getValue(symbol)
            listOf("close","adr20","mdv20").forEach{key->if(original.isNull(key))assertTrue("$symbol $key",row.isNull(key))else assertEquals("$symbol $key",original.getDouble(key),row.getDouble(key),maxOf(1e-8,kotlin.math.abs(original.getDouble(key))*1e-10))}
            listOf("eligible","candidate").forEach{key->assertEquals("$symbol $key",original.getBoolean(key),row.getBoolean(key))}
            listOf("rfl1m_rank","rfl3m_rank","rfl6m_rank").forEach{key->if(original.isNull(key))assertTrue("$symbol $key",row.isNull(key))else assertEquals("$symbol $key",original.getInt(key),row.getInt(key))}
        }
        println("Device full-market parity: ${actual.size} symbols; ${actual.count{it.getBoolean("candidate")}} candidates")
    }
}
