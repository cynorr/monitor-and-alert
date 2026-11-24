package com.cyno.marketmonitor

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import org.json.JSONObject
import org.json.JSONArray
import java.io.File
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import java.util.zip.ZipInputStream

class LocalStore(val context: Context) {
    val root=File(context.filesDir,"market")
    val daily=File(root,"massive/daily.sqlite3")
    val calendar=SessionCalendar(asset("sessions.json"))
    val config=asset("scan.json")
    fun asset(name:String)=JSONObject(context.assets.open(name).bufferedReader().use{it.readText()})
    fun read(path:String)=JSONObject(File(root,path).readText())
    fun write(path:String,data:JSONObject) { val f=File(root,path);f.parentFile?.mkdirs();f.writeText(data.toString()) }
    fun initialize(progress:(String)->Unit) {
        if(File(root,".installed").exists())return
        root.mkdirs();var count=0
        ZipInputStream(context.assets.open("seed.zip").buffered(1024*1024)).use { zip ->
            while(true) {
                val entry=zip.nextEntry?:break;val target=File(root,entry.name)
                require(target.canonicalPath.startsWith(root.canonicalPath+File.separator)) { "Invalid seed path" }
                if(entry.isDirectory)target.mkdirs() else {
                    target.parentFile?.mkdirs();var copied=0L
                    target.outputStream().buffered(1024*1024).use{output->
                        val buffer=ByteArray(256*1024)
                        while(true){val size=zip.read(buffer);if(size<0)break;output.write(buffer,0,size);copied+=size
                            if(copied%(32*1024*1024)<size)progress("Preparing local history · ${target.name} · ${copied/1024/1024} MiB")
                        }
                    }
                }
                zip.closeEntry();count++;if(count%20==0)progress("Preparing local history · $count files")
            }
        }
        require(daily.exists() && File(root,"preferences.json").exists()){"Incomplete initial dataset"}
        // The imported raw files have Android mtimes; establish this device's manifest without changing market values.
        openDaily(true).use { db ->
            meta(db,"android_raw_files",manifest().toString())
            meta(db,"android_split_revision",digest(canonical(read("massive/splits.json").getJSONArray("results"))))
        }
        File(root,".installed").writeText("1")
    }
    fun manifest()=JSONObject().apply { File(root,"massive/daily").listFiles()?.filter{it.extension=="json"}?.sortedBy{it.name}?.forEach{put(it.name,"${it.length()}:${it.lastModified()}")} }
    fun openDaily(write:Boolean=false):SQLiteDatabase=SQLiteDatabase.openDatabase(daily.path,null,if(write)SQLiteDatabase.OPEN_READWRITE else SQLiteDatabase.OPEN_READONLY)
    fun metadata(db:SQLiteDatabase,key:String):String?=db.rawQuery("SELECT value FROM metadata WHERE key=?",arrayOf(key)).use{if(it.moveToFirst())it.getString(0)else null}
    fun meta(db:SQLiteDatabase,key:String,value:String)=db.execSQL("INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)",arrayOf(key,value))
    fun completed():String=openDaily().use{metadata(it,"completed_date")?:error("Daily completion date is missing")}
    fun dates():List<String> = File(root,"days").listFiles()?.filter{File(it,"scan.json").exists()}?.map{it.name}?.sortedDescending()?:emptyList()
    fun latestWorkspaceDate():String = File(root,"days").listFiles()?.filter{File(it,"workspace.json").exists()}?.maxOfOrNull{it.name}?:error("No workspace")
    fun preferences()=read("preferences.json")
    fun bars(symbol:String,day:String,db:SQLiteDatabase?=null):List<DailyBar> = readBars(symbol,day,db,1000)
    fun screeningBars(symbol:String,day:String,db:SQLiteDatabase):List<DailyBar> = readBars(symbol,day,db,maxOf(126,config.getInt("minimum_daily_bars")))
    private fun readBars(symbol:String,day:String,db:SQLiteDatabase?,limit:Int):List<DailyBar> {
        val owned=db?:openDaily()
        try {
            val end=calendar.stamp(LocalDate.parse(day))
            return owned.rawQuery("SELECT ts,open,high,low,close,volume,turnover FROM bars WHERE symbol=? AND timeframe='1d' AND ts<=? ORDER BY ts DESC LIMIT $limit",arrayOf(symbol,end.toString())).use { c ->
                buildList {while(c.moveToNext())add(DailyBar(symbol,c.getLong(0),c.getDouble(1),c.getDouble(2),c.getDouble(3),c.getDouble(4),c.getLong(5),if(c.isNull(6))null else c.getDouble(6)))}.reversed()
            }
        } finally {if(db==null)owned.close()}
    }
    fun search(query:String):List<String> = openDaily().use {db->
        db.rawQuery("SELECT DISTINCT symbol FROM bars WHERE symbol LIKE ? ESCAPE '\\' ORDER BY symbol LIMIT 30",arrayOf(query.uppercase().replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%")).use{c->buildList{while(c.moveToNext())add(c.getString(0).removeSuffix(".US"))}}
    }
    fun workspace(day:String):JSONObject = File(root,"days/$day/workspace.json").let{if(it.exists())JSONObject(it.readText()) else Rules.empty()}
    fun saveWorkspace(day:String,value:JSONObject)=write("days/$day/workspace.json",Rules.persistent(value))
    fun featureMap(day:String):Map<String,JSONObject> = read("days/$day/scan.json").objects("rows").associate{it.getString("symbol").removeSuffix(".US") to it}
    fun generate(day:String,preferences:JSONObject,reset:Boolean,progress:(String)->Unit):Pair<Map<String,JSONObject>,JSONObject> {
        val parsed=LocalDate.parse(day);val previousDay=latestWorkspaceDate();val previous=workspace(previousDay)
        val ws=if(reset||previousDay!=day)Rules.reset(previous,parsed,previousDay!=day)else previous
        val states=ws.getJSONObject("statuses")
        val etfs=read("symbol-directory.json").getJSONObject("symbols")
        val rows=mutableListOf<JSONObject>()
        openDaily().use { db->
            val symbols=db.rawQuery("SELECT symbol FROM bars WHERE timeframe='1d' AND ts=? ORDER BY symbol",arrayOf(calendar.stamp(parsed).toString())).use{c->buildList{while(c.moveToNext())add(c.getString(0))}}
            symbols.forEachIndexed{i,symbol->
                rows.add(ScanMath.metrics(screeningBars(symbol,day,db)));if(i%200==0)progress("Scanning · $i / ${symbols.size}")
            }
            ScanMath.rank(rows,config,etfs)
            val retained=states.entries().filter{(_,v)->(v as JSONObject).let{it.optString("status")=="focus"||Rules.hidden(it,parsed)||(it.optString("status")=="discover"&&it.optString("manual_discover_date")==day)}}.map{it.first}.toSet()
            val features=rows.associateBy{it.getString("symbol").removeSuffix(".US")}.toMutableMap()
            val scope=rows.filter{it.optBoolean("candidate")}.map{it.getString("symbol").removeSuffix(".US")}.toSet()+retained
            scope.forEach {ticker->
                val history=bars("$ticker.US",day,db)
                if(history.isNotEmpty()) {
                    val full=ScanMath.features(history);val row=features[ticker]
                    listOf("eligible","candidate","rfl1m_rank","rfl3m_rank","rfl6m_rank").forEach{key->full.put(key,row?.opt(key)?:JSONObject.NULL)}
                    features[ticker]=full
                }
            }
            val snapshot=json("date" to day,"mock" to false,"rows" to array(features.toSortedMap().values),"feature_scope" to array(scope.sorted()),"input_revision" to metadata(db,"input_revision"))
            write("days/$day/scan.json",snapshot)
            return features to ws
        }
    }
    fun chart(symbol:String,day:String):ChartData {
        val rows=bars(symbol,day);val averages=ScanMath.indicators(rows)
        val byDay=rows.associateBy{it.date}
        val payload=json("symbol" to symbol.removeSuffix(".US"),"date" to day,"rows" to array(rows.mapIndexed{i,b->
            val samples=calendar.previous(b.date).mapNotNull{byDay[it]?.turnover};val mean=samples.takeIf{it.isNotEmpty()}?.average()
            b.toJson().put("day",b.date.toString()).put("ema10",if(i>=9)averages.ema10[i]else JSONObject.NULL)
                .put("ema20",if(i>=19)averages.ema20[i]else JSONObject.NULL).put("sma50",if(i>=49)averages.sma50[i]else JSONObject.NULL)
                .put("comparison",if(mean!=null&&mean>0&&b.turnover!=null)b.turnover/mean*100 else JSONObject.NULL)
        }))
        return ChartData(symbol,day,rows,payload.toString())
    }
}
