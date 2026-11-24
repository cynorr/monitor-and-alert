package com.cyno.marketmonitor

import org.junit.Assert.*
import org.junit.Test
import org.json.*
import java.io.File
import java.time.LocalDate

class ParityTest {
    private fun reference(name:String)=File(System.getProperty("reference.dir"),name)
    @Test fun realIndicatorsMatchPython(){
        val file=reference("features.json");org.junit.Assume.assumeTrue("Run tools/prepare_reference.py",file.exists())
        JSONArray(file.readText()).objects().forEach{case->
            val symbol=case.getString("symbol");val rows=case.getJSONArray("bars")
            val bars=(0 until rows.length()).map{i->val a=rows.getJSONArray(i);DailyBar(symbol,a.getLong(0),a.getDouble(1),a.getDouble(2),a.getDouble(3),a.getDouble(4),a.getLong(5),if(a.isNull(6))null else a.getDouble(6))}
            val actual=ScanMath.features(bars);case.getJSONObject("expected").entries().forEach{(key,expected)->
                val label="$symbol ${bars.size} $key"
                when{expected==JSONObject.NULL->assertTrue(label,actual.isNull(key));expected is Number->{assertNotNull(label,actual.number(key));assertEquals(label,expected.toDouble(),actual.getDouble(key),maxOf(1e-9,kotlin.math.abs(expected.toDouble())*1e-10))};else->assertEquals(label,expected,actual.get(key))}
            }
        }
    }
    @Test fun realClassificationMatchesPython(){
        val file=reference("rules.json");org.junit.Assume.assumeTrue(file.exists());val data=JSONObject(file.readText())
        val features=data.getJSONObject("snapshot").objects("rows").associate{it.getString("symbol").removeSuffix(".US") to it}
        val actual=Rules.classify(data.getJSONObject("workspace"),features,data.getJSONObject("preferences").objects("tags"),LocalDate.parse(data.getString("date")))
        assertEquals(canonical(data.getJSONObject("expected")),canonical(actual))
    }
    @Test fun missingAmountIsNotZeroAndNeverFallsBackToClose(){
        val bars=(0..59).map{i->DailyBar("TEST.US",i.toLong(),10.0,12.0,9.0,11.0,1000,if(i==59)null else 20000.0)}
        assertTrue(ScanMath.features(bars).isNull("mdv20"))
        assertEquals(0.0,ScanMath.features(bars.map{it.copy(turnover=0.0)}).getDouble("mdv20"),0.0)
    }
    @Test fun rankTiesUseSymbolAndFiltersDoNotRefillRanking(){
        val rows=listOf("B.US","A.US","C.US").map{json("symbol" to it,"count" to 50,"close" to 6,"adr20" to 5,"mdv20" to 16000000,"rfl1m" to 50,"rfl3m" to 50,"rfl6m" to 50)}
        val directory=JSONObject().apply{rows.forEach{put(it.getString("symbol"),json("etf" to false))}}
        ScanMath.rank(rows,json("minimum_daily_bars" to 50,"minimum_adr20_percent" to 4,"minimum_mdv20_usd" to 15000000,"close_price_above_usd" to 5,"momentum_top_n" to 1),directory)
        assertEquals(listOf("A.US"),rows.filter{it.getBoolean("candidate")}.map{it.getString("symbol")})
    }
    @Test fun hiddenExpiresAfterSevenCalendarDaysAndFocusCanBeDropped(){
        val day=LocalDate.parse("2026-11-19");val ws=Rules.empty();ws.getJSONObject("statuses").put("H",json("status" to "excluded","section" to "hidden","excluded_at" to "2026-11-12")).put("F",json("status" to "focus","section" to "unclassified"))
        val tag=json("id" to "broken","name" to "Broken","role" to "broken","filters" to json("broken_k" to json("min" to 1)))
        val result=Rules.classify(ws,mapOf("F" to json("candidate" to false,"broken_k" to 2)),listOf(tag),day)
        assertEquals(0,result.getJSONObject("statuses").length())
    }
    @Test fun filterBoundsAndMissingSemantics(){
        assertFalse(Rules.matches(json("x" to null),json("x" to json("max" to 4))))
        assertTrue(Rules.matches(json("x" to 4),json("x" to json("max" to 4))))
        assertFalse(Rules.matches(json("x" to 4),json("x" to json("max" to 4,"maxExclusive" to true))))
        assertTrue(Rules.matches(json("ma_arrangement" to "missing"),json("ma_arrangement" to json("values" to JSONArray(listOf("missing"))))))
    }
}
