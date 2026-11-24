package com.cyno.marketmonitor

import android.database.sqlite.SQLiteDatabase
import kotlinx.coroutines.*
import org.json.*
import java.io.File
import java.net.URI
import java.math.BigDecimal
import java.math.RoundingMode
import java.time.*

class Massive(private val store:LocalStore,private val token:String) {
    private val http=SourceHttp(15000)
    private suspend fun fetch(url:String)=http.json(url,mapOf("Authorization" to "Bearer $token"))
    private fun checkDaily(data:JSONObject,day:LocalDate):List<JSONObject> {
        require(data.optString("status") in listOf("OK","DELAYED") && data.opt("adjusted")==false){"Expected successful unadjusted Daily"}
        val rows=data.objects("results");require(data.getInt("resultsCount")==rows.size&&rows.isNotEmpty()){ "Daily count is invalid" }
        val seen=mutableSetOf<String>()
        rows.forEach{row->
            val symbol=row.getString("T");require(symbol.isNotBlank()&&symbol==symbol.trim()&&seen.add(symbol)&&!row.optBoolean("otc")){"Invalid Daily symbol"}
            listOf("o","h","l","c").forEach{require((row.number(it)?:0.0)>0){"Invalid Daily OHLC"}}
            require(row.number("v")?.let{it>=0}==true){"Invalid Daily volume"}
            require(Instant.ofEpochMilli(row.getLong("t")).atZone(ET).toLocalDate()==day){"Daily timestamp mismatch"}
            if(!row.isNull("vw"))require(row.number("vw")!=null){"Invalid Daily VWAP"}
            if(!row.isNull("n"))require(row.getLong("n")>=0 && row.number("n")==row.getLong("n").toDouble()){"Invalid Daily transaction count"}
        }
        return rows
    }
    private fun checkSplits(rows:List<JSONObject>,start:LocalDate,end:LocalDate):List<JSONObject> {
        val seen=mutableSetOf<String>()
        rows.forEach{row->
            require(row.getString("id").isNotEmpty()&&seen.add(row.getString("id"))){"Duplicate split"}
            require(row.getString("ticker").isNotBlank()&&row.has("adjustment_type")){"Invalid split ticker"}
            require(LocalDate.parse(row.getString("execution_date")) in start..end){"Split coverage mismatch"}
            listOf("split_from","split_to").forEach{require((row.number(it)?:0.0)>0){"Invalid split ratio"}}
        }
        return rows.sortedWith(compareBy<JSONObject>{it.getString("execution_date")}.thenBy{it.getString("ticker")}.thenBy{it.getString("id")})
    }
    suspend fun prepare(progress:(String)->Unit):String = withContext(Dispatchers.IO) {
        val target=store.calendar.target();val day=target.toString()
        require(store.config.getInt("minimum_daily_bars")>=1){"Invalid scan configuration"}
        require(File(store.root,"symbol-directory.json").exists()){"Symbol directory is missing"}
        val directory=File(store.root,"massive/daily").apply{mkdirs()}
        val existing=directory.listFiles()!!.filter{it.extension=="json"}.map{LocalDate.parse(it.nameWithoutExtension)}
        require(existing.maxOrNull()?.let{it<=target}!=false){"Local Daily is later than target"}
        val start=maxOf(target.minusYears(2),existing.maxOrNull()?.minusDays(14)?:target.minusYears(2))
        for(date in store.calendar.days(start,target).reversed()) {
            currentCoroutineContext().ensureActive();val file=File(directory,"$date.json")
            if(file.exists())checkDaily(JSONObject(file.readText()),date)
            else {
                progress("Daily · $date")
                val data=fetch("https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/$date?adjusted=false&include_otc=false")
                checkDaily(data,date);currentCoroutineContext().ensureActive();file.writeText(data.toString())
            }
        }
        val splitFile=File(store.root,"massive/splits.json");val old=if(splitFile.exists())JSONObject(splitFile.readText())else null
        val lower=target.minusYears(2)
        if(old==null||LocalDate.parse(old.getString("end_date"))<target||LocalDate.parse(old.getString("start_date"))>lower) {
            progress("Splits · $day")
            var url:String?="https://api.massive.com/stocks/v1/splits?execution_date.gte=$lower&execution_date.lte=$day&limit=5000&sort=execution_date.asc"
            val seen=mutableSetOf<String>();val fresh=mutableListOf<JSONObject>()
            while(url!=null) {
                val uri=URI(url);require(uri.scheme=="https"&&uri.host=="api.massive.com"&&uri.path=="/stocks/v1/splits"&&seen.add(url)){"Invalid split page"}
                val data=fetch(url);require(data.getString("status")=="OK"){"Split request unsuccessful"}
                fresh.addAll(checkSplits(data.objects("results"),lower,target));url=data.nullable("next_url")
            }
            val kept=old?.objects("results")?.filter{LocalDate.parse(it.getString("execution_date"))<lower}?:emptyList()
            val begin=minOf(lower,old?.let{LocalDate.parse(it.getString("start_date"))}?:lower)
            require(old==null||LocalDate.parse(old.getString("end_date"))>=lower.minusDays(1)){"Split coverage has a gap"}
            val merged=checkSplits(kept+fresh,begin,target)
            store.write("massive/splits.json",json("status" to "OK","start_date" to begin.toString(),"end_date" to day,"resultsCount" to merged.size,"results" to array(merged)))
        }
        build(target,progress);day
    }
    suspend fun build(target:LocalDate,progress:(String)->Unit) = withContext(Dispatchers.IO) {
        val split=store.read("massive/splits.json")
        val splits=checkSplits(split.objects("results"),LocalDate.parse(split.getString("start_date")),LocalDate.parse(split.getString("end_date")))
        require(split.getInt("resultsCount")==splits.size&&LocalDate.parse(split.getString("end_date"))>=target){"Invalid split snapshot"}
        val splitRevision=digest(canonical(array(splits)));val manifest=store.manifest()
        val files=File(store.root,"massive/daily").listFiles()!!.filter{it.extension=="json"&&it.nameWithoutExtension<=target.toString()}.sortedBy{it.name}
        var rebuild=!store.daily.exists();var completed="";var previous=JSONObject();var oldSplit:String?=null
        if(!rebuild)store.openDaily().use{db->completed=store.metadata(db,"completed_date")?:"";previous=JSONObject(store.metadata(db,"android_raw_files")?:"{}");oldSplit=store.metadata(db,"android_split_revision")}
        val added=files.filter{!previous.has(it.name)}
        rebuild=rebuild||previous.length()==0||oldSplit!=splitRevision||previous.entries().any{(name,v)->manifest.optString(name)!=v.toString()}||added.any{it.nameWithoutExtension<=completed}
        val pending=if(rebuild)files else added
        if(pending.isEmpty()&&completed==target.toString())return@withContext
        val bySymbol=splits.groupBy{it.getString("ticker")}
        if(rebuild)store.daily.delete()
        try {
            SQLiteDatabase.openOrCreateDatabase(store.daily,null).use{db->
                if(rebuild) {
                    db.execSQL("CREATE TABLE bars(symbol TEXT NOT NULL,timeframe TEXT NOT NULL,ts INTEGER NOT NULL,open REAL NOT NULL,high REAL NOT NULL,low REAL NOT NULL,close REAL NOT NULL,volume INTEGER NOT NULL,turnover REAL,PRIMARY KEY(symbol,timeframe,ts))")
                    db.execSQL("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
                }
                val insert=db.compileStatement("INSERT OR REPLACE INTO bars VALUES(?,'1d',?,?,?,?,?,?,?)")
                val touched=mutableSetOf<String>()
                pending.forEachIndexed{index,file->
                    currentCoroutineContext().ensureActive();val date=LocalDate.parse(file.nameWithoutExtension)
                    progress("Building bars · ${index+1} / ${pending.size}")
                    require(store.calendar.sessions[date]?.second?.let{it<=Instant.now().epochSecond}==true){"Daily is not closed"}
                    val rows=checkDaily(JSONObject(file.readText()),date)
                    db.beginTransaction()
                    try{rows.forEach{row->
                        val ticker=row.getString("T");var factor=1.0
                        bySymbol[ticker]?.filter{date.toString()<it.getString("execution_date")}?.forEach{factor*=it.getDouble("split_from")/it.getDouble("split_to")}
                        require(factor.isFinite()&&factor>0){"Invalid accumulated split factor"}
                        val rawVolume=row.getDouble("v")/factor
                        val volume=BigDecimal.valueOf(rawVolume).setScale(0,RoundingMode.HALF_UP).longValueExact()
                        val amount=row.number("vw")?.takeIf{it>0}?.let{it*factor*rawVolume}?.takeIf{it.isFinite()}
                        val prices=listOf("o","h","l","c").map{row.getDouble(it)*factor}
                        require(prices.all{it.isFinite()&&it>0}&&volume>=0){"Invalid adjusted bar"}
                        if(prices[2]>minOf(prices[0],prices[3])||prices[1]<maxOf(prices[0],prices[3])||prices[1]<prices[2])File(store.root,"invalid_ohlc.jsonl").appendText(json("source" to "massive","symbol" to "$ticker.US","date" to date.toString(),"open" to prices[0],"high" to prices[1],"low" to prices[2],"close" to prices[3]).toString()+"\n")
                        insert.clearBindings();insert.bindString(1,"$ticker.US");insert.bindLong(2,store.calendar.stamp(date))
                        prices.forEachIndexed{i,v->insert.bindDouble(i+3,v)};insert.bindLong(7,volume);if(amount==null)insert.bindNull(8)else insert.bindDouble(8,amount)
                        insert.executeInsert();touched.add("$ticker.US")
                    };db.setTransactionSuccessful()}finally{db.endTransaction()}
                }
                touched.forEach{symbol->db.execSQL("DELETE FROM bars WHERE symbol=? AND timeframe='1d' AND ts NOT IN(SELECT ts FROM bars WHERE symbol=? AND timeframe='1d' ORDER BY ts DESC LIMIT 1000)",arrayOf(symbol,symbol))}
                store.meta(db,"completed_date",target.toString());store.meta(db,"android_raw_files",manifest.toString());store.meta(db,"android_split_revision",splitRevision)
                store.meta(db,"input_revision",digest(canonical(manifest)+splitRevision));store.meta(db,"source","massive_grouped_daily");store.meta(db,"session","massive_daily")
                store.meta(db,"adjustment","split_adjusted");store.meta(db,"volume_rounding","half_up");store.meta(db,"turnover","vwap_times_unrounded_volume")
                insert.close()
            }
        } catch(e:Exception){store.daily.delete();throw e}
    }
}
