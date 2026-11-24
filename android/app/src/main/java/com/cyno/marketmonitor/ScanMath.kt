package com.cyno.marketmonitor

import org.json.JSONObject
import kotlin.math.*

/** Direct translation of indicators.py and features/atomic.py. NaN becomes a missing JSON value. */
object ScanMath {
    data class Indicators(val ema10: DoubleArray, val ema20: DoubleArray, val sma50: DoubleArray, val tr: DoubleArray, val atr: DoubleArray)
    fun median(values: List<Double>): Double {
        if(values.isEmpty() || values.any { !it.isFinite() }) return Double.NaN
        val sorted=values.sorted(); return (sorted[(sorted.size-1)/2]+sorted[sorted.size/2])/2
    }
    fun indicators(bars: List<DailyBar>): Indicators {
        val n=bars.size; val e10=DoubleArray(n);val e20=DoubleArray(n);val sma=DoubleArray(n){Double.NaN}
        val tr=DoubleArray(n);val atr=DoubleArray(n){Double.NaN}
        var sum=0.0
        bars.forEachIndexed { i,b ->
            e10[i]=if(i==0)b.close else 2.0/11*b.close+(1-2.0/11)*e10[i-1]
            e20[i]=if(i==0)b.close else 2.0/21*b.close+(1-2.0/21)*e20[i-1]
            sum+=b.close;if(i>=50)sum-=bars[i-50].close;if(i>=49)sma[i]=sum/50
            tr[i]=if(i==0)b.high-b.low else maxOf(b.high-b.low,abs(b.high-bars[i-1].close),abs(b.low-bars[i-1].close))
            if(i==19)atr[i]=(0..19).sumOf { tr[it] }/20
            else if(i>=20)atr[i]=.05*tr[i]+.95*atr[i-1]
        }
        return Indicators(e10,e20,sma,tr,atr)
    }
    fun features(bars: List<DailyBar>): JSONObject {
        require(bars.isNotEmpty());val n=bars.size;val last=bars.last();val a=indicators(bars)
        val out=last.toJson().put("date",last.date.toString())
        fun put(key:String,value:Double) {out.put(key,if(value.isFinite())value else JSONObject.NULL)}
        put("ema10",a.ema10.last());put("ema20",a.ema20.last());put("sma50",a.sma50.last());put("atr20",a.atr.last())
        put("adr20",bars.takeLast(20).map { (it.high-it.low)/it.low*100 }.average())
        put("mdv20",median(bars.takeLast(20).map { it.turnover ?: Double.NaN }))
        listOf("rfl1m" to 21,"rfl3m" to 63,"rfl6m" to 126).forEach { (key,size) -> put(key,(last.close/bars.takeLast(size).minOf { it.low }-1)*100) }
        val e10=a.ema10.last();val e20=a.ema20.last();val s50=a.sma50.last()
        out.put("ma_arrangement",when { !s50.isFinite()->"missing";e10==e20||e10==s50||e20==s50->"others";e10>e20&&e20>s50->"ema10_lead";e20>e10&&e10>s50->"ema20_lead";s50>max(e10,e20)->"under50";else->"straddle" })
        put("extended_k",(last.close-max(e10,e20))/a.atr.last());put("broken_k",(min(e10,e20)-last.close)/a.atr.last())
        out.put("below_days",bars.indices.reversed().takeWhile { bars[it].close<min(a.ema10[it],a.ema20[it]) }.size)
        fun slope(values: List<Double>):Double = if(values.size<5||values.any { !it.isFinite() }) Double.NaN else
            median((0..3).flatMap { i -> (i+1..4).map { j -> (values[j]-values[i])/(j-i) } })/last.close*100
        val tail=bars.takeLast(5)
        mapOf("low" to tail.map{it.low},"high" to tail.map{it.high},"body_low" to tail.map{min(it.open,it.close)},
            "body_high" to tail.map{max(it.open,it.close)},"close" to tail.map{it.close},"ema10" to a.ema10.takeLast(5),
            "ema20" to a.ema20.takeLast(5),"sma50" to a.sma50.takeLast(5)).forEach { (key,values) -> put("${key}_slope_5d",slope(values)) }
        put("body_range_k_5d",if(n<5)Double.NaN else (tail.maxOf{max(it.open,it.close)}-tail.minOf{min(it.open,it.close)})/a.atr.last())
        put("close_range_k_5d",if(n<5)Double.NaN else (tail.maxOf{it.close}-tail.minOf{it.close})/a.atr.last())
        put("median_true_range_k_5d",if(n<5)Double.NaN else median((n-5 until n).map { a.tr[it]/a.atr[it] }))
        listOf("ema10" to a.ema10,"ema20" to a.ema20).forEach { (name,ma) ->
            val low=bars.indices.map { (bars[it].low-ma[it])/a.atr[it] }
            val below=bars.indices.map { bars[it].close<ma[it] }
            val down=bars.indices.map { it>0 && bars[it-1].close>=ma[it-1] && below[it] }
            val cross=bars.indices.map { it>0 && ((bars[it-1].close>=ma[it-1]&&below[it])||(bars[it-1].close<ma[it-1]&&!below[it])) }
            val reclaim=bars.indices.map { bars[it].low<ma[it]&&!below[it] }
            fun count(key:String,values:List<Boolean>) { out.put("${name}_$key",if(n>=5)values.takeLast(5).count{it} else JSONObject.NULL) }
            fun since(key:String,values:List<Boolean>) {val i=values.indexOfLast{it};out.put("${name}_$key",if(i<0)JSONObject.NULL else n-1-i)}
            put("${name}_close_distance_k",(last.close-ma.last())/a.atr.last());put("${name}_low_distance_k",low.last())
            put("${name}_low_abs_distance_median_k_5d",if(n<5)Double.NaN else median(low.takeLast(5).map{abs(it)}))
            if(a.atr.takeLast(5).any{!it.isFinite()})out.put("${name}_touch_days_5d",JSONObject.NULL)
            else count("touch_days_5d",bars.indices.map { abs(bars[it].low-ma[it])<=.5*a.atr[it] })
            count("close_below_days_5d",below);count("reclaim_count_5d",reclaim)
            since("days_since_close_downcross",down);since("days_since_reclaim",reclaim)
            out.put("${name}_close_cross_count_5d",if(n>=5)cross.takeLast(4).count{it} else JSONObject.NULL)
            put("${name}_max_penetration_k_5d",if(n<5||low.takeLast(5).any{!it.isFinite()})Double.NaN else low.takeLast(5).maxOf{max(-it,0.0)})
        }
        return out
    }
    fun metrics(bars: List<DailyBar>): JSONObject {
        val out=json("symbol" to bars.last().symbol,"close" to bars.last().close,"count" to bars.size)
        val recent=bars.takeLast(20)
        out.put("adr20",recent.map{(it.high-it.low)/it.low*100}.average())
        val amount=median(recent.map{it.turnover?:Double.NaN});out.put("mdv20",if(amount.isFinite())amount else JSONObject.NULL)
        listOf("rfl1m" to 21,"rfl3m" to 63,"rfl6m" to 126).forEach{(key,size)->out.put(key,(bars.last().close/bars.takeLast(size).minOf{it.low}-1)*100)}
        return out
    }
    fun rank(rows: List<JSONObject>, config: JSONObject, etfs: JSONObject) {
        rows.forEach{row->row.put("eligible",row.getInt("count")>=config.getInt("minimum_daily_bars") &&
            etfs.optJSONObject(row.getString("symbol"))?.optBoolean("etf",true)==false &&
            row.getDouble("adr20")>=config.getDouble("minimum_adr20_percent") &&
            (row.number("mdv20")?:Double.NEGATIVE_INFINITY)>=config.getDouble("minimum_mdv20_usd") &&
            row.getDouble("close")>config.getDouble("close_price_above_usd"))}
        listOf("rfl1m","rfl3m","rfl6m").forEach{key->rows.filter{it.optBoolean("eligible")}.sortedWith(compareByDescending<JSONObject>{it.getDouble(key)}.thenBy{it.getString("symbol")}).forEachIndexed{i,row->row.put("${key}_rank",i+1)}}
        rows.forEach{row->row.put("candidate",listOf("rfl1m","rfl3m","rfl6m").any{row.optInt("${it}_rank",Int.MAX_VALUE)<=config.getInt("momentum_top_n")})}
    }
}
