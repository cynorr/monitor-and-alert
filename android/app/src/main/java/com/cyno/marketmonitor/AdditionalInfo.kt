package com.cyno.marketmonitor

import android.database.sqlite.SQLiteDatabase
import kotlinx.coroutines.*
import org.json.*
import java.io.File
import java.time.*
import java.time.temporal.ChronoUnit

class AdditionalInfo(private val store:LocalStore) {
    private val path=File(store.root,"additional-info/info.sqlite3")
    private val http=SourceHttp(1000)
    private val headers=mapOf("User-Agent" to "Mozilla/5.0","Accept" to "application/json","Origin" to "https://www.nasdaq.com","Referer" to "https://www.nasdaq.com/")
    private val companies=mutableMapOf<String,JSONObject>();private val days=sortedMapOf<String,String>()
    private val events=mutableMapOf<String,List<JSONObject>>();private val metadata=mutableMapOf<String,String>()
    private val cleaning=store.asset("company-name-patterns.json")
    fun load() {
        path.parentFile?.mkdirs()
        SQLiteDatabase.openOrCreateDatabase(path,null).use{db->
            db.execSQL("CREATE TABLE IF NOT EXISTS companies(symbol TEXT PRIMARY KEY,payload TEXT NOT NULL)")
            db.execSQL("CREATE TABLE IF NOT EXISTS earnings_days(date TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at TEXT NOT NULL)")
            db.execSQL("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            db.rawQuery("SELECT key,value FROM metadata",null).use{c->while(c.moveToNext())metadata[c.getString(0)]=c.getString(1)}
            db.rawQuery("SELECT symbol,payload FROM companies",null).use{c->while(c.moveToNext())companies[c.getString(0)]=JSONObject(c.getString(1))}
            db.rawQuery("SELECT date,payload,updated_at FROM earnings_days ORDER BY date",null).use{c->while(c.moveToNext()){val day=c.getString(0);days[day]=c.getString(2);replaceEvents(day,parseEarnings(JSONObject(c.getString(1)),day))}}
        }
    }
    private fun rows(data:JSONObject,empty:Boolean=false):List<JSONObject> {
        require(data.optJSONObject("status")?.optInt("rCode",200)!=null && data.getJSONObject("status").optInt("rCode",200)==200 || data.isNull("status")){"Nasdaq returned unsuccessful status"}
        if(data.isNull("data")&&empty)return emptyList()
        val body=data.getJSONObject("data")
        if(body.isNull("rows")&&empty)return emptyList()
        val rows=body.objects("rows");require(rows.isNotEmpty()||empty){"Nasdaq returned no company rows"}
        rows.forEach{require(it.opt("symbol") is String){"Nasdaq symbol is missing"}};return rows
    }
    private fun text(value:Any?):String? = (value as? String)?.trim()?.replace(Regex("\\s+")," ")?.takeUnless{it.isEmpty()||it.uppercase() in listOf("N/A","NA","--","NAN")}
    private fun number(value:Any?):Double?=value?.toString()?.replace("$","")?.replace(",","")?.let{if(it.startsWith("(")&&it.endsWith(")"))"-"+it.substring(1,it.length-1)else it}?.toDoubleOrNull()?.takeIf{it.isFinite()}
    private fun symbol(row:JSONObject)=text(row.opt("symbol"))?.takeIf{Regex("[A-Z][A-Z0-9.-]{0,19}").matches(it)&&!it.endsWith(".US")}?.plus(".US")
    private fun companyName(raw:Any?):String? {
        var value=text(raw)?:return null
        Regex(cleaning.getString("PREFERRED_NOTES"),RegexOption.IGNORE_CASE).matchEntire(value)?.let{value=it.groupValues[1]+it.groupValues[2]}
        listOf("COUPON_SUFFIX","RATE_SUFFIX","SECURITY_SUFFIX").forEach{value=Regex(cleaning.getString(it),RegexOption.IGNORE_CASE).replace(value,"")}
        return value.trimEnd(' ','-').takeIf{it.isNotEmpty()}
    }
    private fun parseEarnings(data:JSONObject,day:String):List<JSONObject> {
        val seen=mutableSetOf<String>()
        return rows(data,true).mapNotNull{row->symbol(row)?.let{key->
            val period=text(row.opt("fiscalQuarterEnding"));require(seen.add("$key/$period")){"Duplicate earnings event"}
            json("symbol" to key,"date" to day,"session" to text(row.opt("time")),"fiscal_period" to period,"reported" to (number(row.opt("eps"))!=null),"raw" to row)
        }}
    }
    @Synchronized private fun replaceEvents(day:String,values:List<JSONObject>) {
        events.keys.toList().forEach{key->events[key]=events.getValue(key).filter{it.getString("date")!=day}}
        values.forEach{event->val symbol=event.getString("symbol");events[symbol]=(events[symbol]?:emptyList())+event}
    }
    @Synchronized fun next(symbol:String,today:LocalDate=todayET()):LocalDate?=events[symbol]?.filter{!it.getBoolean("reported")&&it.getString("date")>=today.toString()}?.minOfOrNull{LocalDate.parse(it.getString("date"))}
    @Synchronized fun enrich(features:Map<String,JSONObject>,retained:Set<String> = emptySet()):Map<String,JSONObject> = (features.keys+retained).associateWith{ticker->
        val row=features[ticker]?:JSONObject()
        if(row.optBoolean("candidate")||row.has("ema10")||ticker in retained)row.copy().put("days_to_earnings",next("$ticker.US")?.let{ChronoUnit.DAYS.between(todayET(),it)}?:JSONObject.NULL)else row
    }
    @Synchronized fun info(symbol:String):JSONObject {
        val company=companies[symbol]?.copy()?:JSONObject();val list=events[symbol]?:emptyList();val today=todayET().toString()
        val last=list.filter{it.getBoolean("reported")&&it.getString("date")<=today}.maxByOrNull{it.getString("date")}
        return company.put("last_earnings",last?.getString("date")?:JSONObject.NULL).put("next_earnings",next(symbol)?.toString()?:JSONObject.NULL)
    }
    private fun localDay(value:String)=Instant.parse(value).atZone(ET).toLocalDate()
    suspend fun refresh(force:Boolean=false,progress:(String)->Unit,onChange:()->Unit) = withContext(Dispatchers.IO) {
        val today=todayET();var companyError:Exception?=null
        if(force||metadata["companies_updated_at"]?.let{localDay(it)!=today}!=false)try {
            progress("Company information")
            val data=http.json("https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true",headers)
            val fresh=mutableMapOf<String,JSONObject>()
            rows(data).forEach{row->
                require(listOf("name","sector","industry","marketCap").all{row.has(it)}){"Nasdaq company columns changed"}
                symbol(row)?.let{key->require(!fresh.containsKey(key)){"Duplicate company symbol"};fresh[key]=json("company_name" to companyName(row.opt("name")),"raw_name" to row.opt("name"),"sector" to text(row.opt("sector")),"industry" to text(row.opt("industry")),"market_cap" to number(row.opt("marketCap"))?.takeIf{it>0}?.toString(),"raw" to row)}
            }
            require(fresh.isNotEmpty()){ "No supported companies" };val updated=Instant.now().toString()
            SQLiteDatabase.openOrCreateDatabase(path,null).use{db->db.beginTransaction();try{db.execSQL("DELETE FROM companies");fresh.forEach{(symbol,value)->db.execSQL("INSERT INTO companies VALUES(?,?)",arrayOf(symbol,value.toString()))};db.execSQL("INSERT OR REPLACE INTO metadata VALUES('companies_updated_at',?)",arrayOf(updated));db.setTransactionSuccessful()}finally{db.endTransaction()}}
            synchronized(this@AdditionalInfo){companies.clear();companies.putAll(fresh)};metadata["companies_updated_at"]=updated;onChange()
        }catch(e:CancellationException){throw e}catch(e:Exception){companyError=e}
        fun dates(from:Int,to:Int)=(from..to).map{today.plusDays(it.toLong()).toString()}
        val recent=dates(-7,45).filter{force||days[it]?.let{stamp->localDay(stamp)!=today}!=false}
        val history=dates(-120,-8).reversed().filter{it !in days}
        val weeklyDue=force||metadata["earnings_weekly_at"]?.let{ChronoUnit.DAYS.between(localDay(it),today)>=7}!=false
        val far=if(weeklyDue)dates(46,120).filter{force||days[it]?.let{stamp->ChronoUnit.DAYS.between(localDay(stamp),today)>=7}!=false}else emptyList()
        val planned=recent+history+far
        planned.forEachIndexed{index,day->
            currentCoroutineContext().ensureActive();progress("Earnings · ${index+1}/${planned.size} · $day")
            val data=http.json("https://api.nasdaq.com/api/calendar/earnings?date=$day",headers);val parsed=parseEarnings(data,day);val updated=Instant.now().toString()
            SQLiteDatabase.openOrCreateDatabase(path,null).use{db->db.execSQL("INSERT OR REPLACE INTO earnings_days VALUES(?,?,?)",arrayOf(day,data.toString(),updated))}
            replaceEvents(day,parsed);days[day]=updated;onChange()
        }
        if(weeklyDue){val now=Instant.now().toString();SQLiteDatabase.openOrCreateDatabase(path,null).use{it.execSQL("INSERT OR REPLACE INTO metadata VALUES('earnings_weekly_at',?)",arrayOf(now))};metadata["earnings_weekly_at"]=now}
        companyError?.let{throw it}
    }
    suspend fun updateDirectory()=withContext(Dispatchers.IO) {
        val symbols=JSONObject()
        listOf("nasdaqlisted.txt" to "Symbol","otherlisted.txt" to "ACT Symbol").forEach{(name,column)->
            val lines=http.text("https://www.nasdaqtrader.com/dynamic/SymDir/$name").lineSequence().filter{it.isNotBlank()}.toList()
            val header=lines.first().split('|');val index=header.indexOf(column);val etf=header.indexOf("ETF")
            require(index>=0&&etf>=0&&lines.last().startsWith("File Creation Time:")){"Invalid Nasdaq directory header/footer"}
            lines.drop(1).dropLast(1).forEach{line->val fields=line.split('|');require(fields.size==header.size&&fields[etf] in listOf("Y","N")){"Invalid directory row"};val key=fields[index]+".US";require(!symbols.has(key)){"Duplicate directory symbol"};symbols.put(key,json("etf" to (fields[etf]=="Y")))}
        }
        store.write("symbol-directory.json",json("symbols" to symbols,"updated_at" to Instant.now().toString()))
    }
}
