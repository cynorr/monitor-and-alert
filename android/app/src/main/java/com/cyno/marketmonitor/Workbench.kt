package com.cyno.marketmonitor

import android.app.Application
import androidx.compose.runtime.*
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import org.json.*
import java.time.LocalDate

class Workbench(application:Application):AndroidViewModel(application) {
    val store=LocalStore(application);val credentials=Credentials(application);val additional=AdditionalInfo(store)
    var initialized by mutableStateOf(false);private set
    var busy by mutableStateOf(true);private set
    var progress by mutableStateOf("Preparing local history");private set
    var error by mutableStateOf<String?>(null);private set
    var infoStatus by mutableStateOf("");private set
    var quoteStatus by mutableStateOf("Quote paused");private set
    var authorized by mutableStateOf(false);private set
    var day by mutableStateOf("");private set
    var latest by mutableStateOf("");private set
    var dates by mutableStateOf(emptyList<String>());private set
    var preferences by mutableStateOf(JSONObject());private set
    var workspace by mutableStateOf(Rules.empty());private set
    var features by mutableStateOf<Map<String,JSONObject>>(emptyMap());private set
    var activeList by mutableStateOf("focus");private set
    var activeTag by mutableStateOf<String?>(null);private set
    var sort by mutableStateOf("default");private set
    var filters by mutableStateOf(JSONObject());private set
    var selected by mutableStateOf("");private set
    var chart by mutableStateOf<ChartData?>(null);private set
    var info by mutableStateOf(JSONObject());private set
    var searchResults by mutableStateOf(emptyList<String>());private set
    val quotes=mutableStateMapOf<String,Quote>()
    private var rawFeatures=emptyMap<String,JSONObject>()
    private var latestSymbols=emptySet<String>()
    private var foreground=false;private var started=false;private var cred:JSONObject?=null
    private var live:LongbridgeQuotes?=null;private var pipeline:Job?=null;private var infoJob:Job?=null;private var selectJob:Job?=null;private var searchJob:Job?=null;private var dayJob:Job?=null
    val tags:List<JSONObject> get()=preferences.objects("tags")
    val historical:Boolean get()=day!=latest
    init{viewModelScope.launch{
        try {
            withContext(Dispatchers.IO){store.initialize{value->viewModelScope.launch{progress=value}};additional.load();cred=credentials.load()}
            authorized=cred!=null;preferences=withContext(Dispatchers.IO){store.preferences()};activeList=preferences.optString("activeList","focus");activeTag=preferences.nullable("activeTag");sort=preferences.optString("sort","default")
            latest=withContext(Dispatchers.IO){store.latestWorkspaceDate()};loadDay(latest)
            initialized=true;busy=false;progress="";if(foreground)startForegroundTasks()
        }catch(e:Exception){busy=false;error="Initial data could not be opened · ${safe(e)}"}
    }}
    private fun safe(e:Exception):String=when(e){is org.json.JSONException->"Invalid data format";is java.io.IOException->if(e.message?.startsWith("HTTP ")==true)e.message!! else "Network or file access failed";else->e.message?.takeUnless{it.contains("http")||it.length>180}?:e.javaClass.simpleName}
    private suspend fun loadDay(value:String) {
        val (raw,ws)=withContext(Dispatchers.IO){
            val snapshot=java.io.File(store.root,"days/$value/scan.json")
            if(snapshot.exists())store.featureMap(value) to store.workspace(value)else store.generate(value,preferences,false){text->viewModelScope.launch{progress=text}}
        }
        day=value;rawFeatures=raw;workspace=ws;reclassify();dates=withContext(Dispatchers.IO){store.dates()}
        if(value==latest)latestSymbols=workspace.getJSONObject("statuses").keys().asSequence().map{"$it.US"}.toSet()
        val available=rows();if(selected.isEmpty()||features[selected]==null)selected=available.firstOrNull()?.ticker?:""
        select(selected);syncQuotes()
    }
    private fun reclassify(){features=if(historical)rawFeatures else additional.enrich(rawFeatures,workspace.getJSONObject("statuses").keys().asSequence().toSet());workspace=Rules.classify(workspace,features,tags,LocalDate.parse(day));if(day==latest){latestSymbols=workspace.getJSONObject("statuses").keys().asSequence().map{"$it.US"}.toSet();syncQuotes()}}
    fun rows():List<ListRow> {
        val states=workspace.getJSONObject("statuses");val pinned=workspace.strings("pinned")
        val values=workspace.getJSONObject("orders").strings(activeList).mapNotNull{ticker->states.optJSONObject(ticker)?.let{state->ListRow(ticker,state.getString("status"),state.optString("section","unclassified"),state.strings("tags"),features[ticker]?:JSONObject(),ticker in pinned)}}
            .filter{row->(activeTag==null||activeTag in row.tags)&&Rules.matches(row.feature,filters)}
        val pinnedRows=pinned.mapNotNull{ticker->values.firstOrNull{it.ticker==ticker}}
        val normal=values.filter{!it.pinned};return pinnedRows+if(sort=="default")normal else normal.sortedWith(compareByDescending<ListRow>{it.feature.number(sort)?:Double.NEGATIVE_INFINITY}.thenBy{it.ticker})
    }
    fun setList(value:String){activeList=value;savePreferences();val visible=rows();if(visible.none{it.ticker==selected})select(visible.firstOrNull()?.ticker?:"")}
    fun setTag(value:String?){activeTag=if(activeTag==value)null else value;savePreferences();if(rows().none{it.ticker==selected})select(rows().firstOrNull()?.ticker?:"")}
    fun chooseSort(value:String){sort=value;savePreferences()}
    fun applyFilters(value:JSONObject){filters=value;if(rows().none{it.ticker==selected})select(rows().firstOrNull()?.ticker?:"")}
    private fun savePreferences(){val value=preferences.copy().put("activeList",activeList).put("activeTag",activeTag?:JSONObject.NULL).put("sort",sort);preferences=value;viewModelScope.launch(Dispatchers.IO){store.write("preferences.json",value)}}
    fun select(ticker:String){selected=ticker;selectJob?.cancel();chart=null;info=JSONObject();if(ticker.isEmpty())return;val identity=ticker;val date=day;selectJob=viewModelScope.launch{try{val data=withContext(Dispatchers.IO){store.chart("$ticker.US",date)};if(selected==identity&&day==date){chart=data;info=additional.info("$ticker.US")}}catch(e:CancellationException){throw e}catch(e:Exception){if(selected==identity){chart=null;error=safe(e)}}}}
    fun search(value:String){searchJob?.cancel();if(value.isBlank()){searchResults=emptyList();return};searchJob=viewModelScope.launch{delay(150);searchResults=withContext(Dispatchers.IO){store.search(value.trim())}}}
    fun chooseSearch(ticker:String){searchResults=emptyList();if(historical){select(ticker);return};viewModelScope.launch{try{
        if(features[ticker]?.has("ema10")!=true){val row=withContext(Dispatchers.IO){store.bars("$ticker.US",day).takeIf{it.isNotEmpty()}?.let{ScanMath.features(it)}}?:error("No local history");rawFeatures=rawFeatures+(ticker to row);features=additional.enrich(rawFeatures)}
        val state=workspace.getJSONObject("statuses").optJSONObject(ticker)
        if(state==null)mutate(ticker,"discover")else if(state.optString("status")=="discover")mutate(ticker,"pin")
        activeList=workspace.getJSONObject("statuses").optJSONObject(ticker)?.optString("status")?:activeList;savePreferences();select(ticker)
    }catch(e:Exception){error=safe(e)}}}
    fun action(ticker:String,action:String){if(historical)return;viewModelScope.launch{try{mutate(ticker,action)}catch(e:Exception){error=safe(e)}}}
    private suspend fun mutate(ticker:String,action:String) {
        val next=workspace.copy();val states=next.getJSONObject("statuses");val old=states.optJSONObject(ticker);val pinned=next.strings("pinned").toMutableList();var moved=false
        when(action){
            "pin"->{if(ticker in pinned)pinned.remove(ticker)else pinned.add(0,ticker)}
            "focus"->{val matches=Rules.matched(features[ticker]?:JSONObject(),tags);states.put(ticker,json("status" to "focus","section" to (matches.firstOrNull{Rules.role(it)=="setup"}?.getString("id")?:"unclassified"),"status_at" to day,"manual_focus_date" to day,"tags" to array(matches.map{it.getString("id")})));moved=true}
            "hide"->{states.put(ticker,json("status" to "excluded","section" to "hidden","status_at" to day,"excluded_at" to day,"tags" to JSONArray()));moved=true}
            "release","discover","release-focus"->{
                if(action=="release"&&old?.optString("section")!="hidden")return
                val row=features[ticker]
                if(action=="discover"&&old==null)states.put(ticker,json("status" to "discover","section" to "unclassified","status_at" to day,"manual_discover_date" to day,"tags" to JSONArray())).also{pinned.add(0,ticker)}
                else if(row?.optBoolean("candidate")==true)states.put(ticker,json("status" to "discover","section" to "unclassified","status_at" to day,"tags" to JSONArray()))
                else states.remove(ticker)
                moved=true
            }
        }
        if(moved){pinned.remove(ticker);if(action=="discover"&&old==null)pinned.add(0,ticker);val orders=next.getJSONObject("orders");listOf("discover","focus","excluded").forEach{status->val order=orders.strings(status).filter{it!=ticker};orders.put(status,array(if(states.optJSONObject(ticker)?.optString("status")==status)listOf(ticker)+order else order))}}
        next.put("pinned",array(pinned));workspace=Rules.classify(next,features,tags,LocalDate.parse(day))
        val saved=workspace.copy();withContext(Dispatchers.IO){store.saveWorkspace(day,saved);val snapshot=store.read("days/$day/scan.json");store.write("days/$day/scan.json",snapshot.put("rows",array(rawFeatures.values)))}
        latestSymbols=workspace.getJSONObject("statuses").keys().asSequence().map{"$it.US"}.toSet();syncQuotes()
        if(rows().none{it.ticker==selected})select(rows().firstOrNull()?.ticker?:"")
    }
    fun chooseDate(value:String){if(busy||value==day)return;viewModelScope.launch{busy=true;try{loadDay(value)}catch(e:Exception){error=safe(e)}finally{busy=false}}}
    fun refresh(explicit:Boolean=true) {
        if(!initialized||pipeline?.isActive==true)return
        if(cred==null){error="Import credentials to update Scan and connect quotes";return}
        pipeline=viewModelScope.launch{busy=true;error=null;try{
            val target=withContext(Dispatchers.IO){Massive(store,cred!!.getJSONObject("massive").getString("api_key")).prepare{value->viewModelScope.launch{progress=value}}}
            val snapshot=java.io.File(store.root,"days/$target/scan.json")
            val ready=withContext(Dispatchers.IO){snapshot.exists()&&JSONObject(snapshot.readText()).nullable("input_revision")==store.openDaily().use{store.metadata(it,"input_revision")}}
            if(explicit||!ready){val (raw,ws)=withContext(Dispatchers.IO){store.generate(target,preferences,explicit){value->viewModelScope.launch{progress=value}}};val classified=Rules.classify(ws,additional.enrich(raw,ws.getJSONObject("statuses").keys().asSequence().toSet()),tags,LocalDate.parse(target));withContext(Dispatchers.IO){store.saveWorkspace(target,classified)}}
            val browsingHistory=historical;latest=target;if(explicit||!browsingHistory)loadDay(target)else{dates=withContext(Dispatchers.IO){store.dates()};latestSymbols=withContext(Dispatchers.IO){val raw=store.featureMap(target);Rules.classify(store.workspace(target),additional.enrich(raw),tags,LocalDate.parse(target)).getJSONObject("statuses").keys().asSequence().map{"$it.US"}.toSet()};syncQuotes()}
        }catch(e:CancellationException){throw e}catch(e:Exception){error="Scan · ${safe(e)}"}finally{busy=false;progress=""}}
    }
    private fun refreshInfo(force:Boolean=false){if(infoJob?.isActive==true)return;infoJob=viewModelScope.launch{try{additional.refresh(force,{value->viewModelScope.launch{infoStatus=value}},{viewModelScope.launch{if(initialized){reclassify();if(selected.isNotEmpty())info=additional.info("$selected.US")}}});infoStatus=""}catch(e:CancellationException){throw e}catch(e:Exception){infoStatus="Additional Info · ${safe(e)}"}}}
    fun importCredentials(value:String){viewModelScope.launch{try{withContext(Dispatchers.IO){credentials.import(JSONObject(value));cred=credentials.load()};authorized=true;live?.close();live=null;if(foreground){startForegroundTasks();refresh(false)}}catch(e:Exception){error="Credentials could not be imported"}}}
    private fun syncQuotes(){live?.update(latestSymbols)}
    fun resume(){foreground=true;if(initialized)startForegroundTasks()}
    fun pause(){foreground=false;live?.close();live=null;pipeline?.cancel();infoJob?.cancel();dayJob?.cancel()}
    private fun startForegroundTasks(){
        if(cred!=null&&live==null){live=LongbridgeQuotes(cred!!.getJSONObject("longbridge").objects("accounts").single(),{symbol,quote->viewModelScope.launch{val old=quotes[symbol];if(old==null||quote.timestamp>=old.timestamp)quotes[symbol]=quote.copy(previousClose=quote.previousClose?:old?.previousClose)}},{value->viewModelScope.launch{quoteStatus=value}}).also{it.start(latestSymbols)}}
        if(!started){started=true;if(cred!=null)refresh(false)}
        refreshInfo();dayJob?.cancel();dayJob=viewModelScope.launch{var last=todayET();while(isActive){delay(30000);if(todayET()!=last){last=todayET();reclassify();refreshInfo()}}}
    }
    fun clearError(){error=null}
    fun refreshAdditional(){refreshInfo(true)}
    fun updateDirectory(){if(busy)return;viewModelScope.launch{try{infoStatus="Updating symbol directory";additional.updateDirectory();infoStatus="Symbol directory updated"}catch(e:Exception){infoStatus="Symbol directory · ${safe(e)}"}}}
}
