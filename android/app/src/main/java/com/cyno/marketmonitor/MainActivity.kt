package com.cyno.marketmonitor

import android.os.Bundle
import android.webkit.*
import android.content.Intent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import org.json.*
import java.time.*
import java.time.temporal.ChronoUnit
import java.util.Locale

class MainActivity:ComponentActivity(){
    private val model:Workbench by viewModels()
    private val importer=registerForActivityResult(ActivityResultContracts.OpenDocument()){uri->if(uri!=null)try{contentResolver.openInputStream(uri)?.bufferedReader()?.use{model.importCredentials(it.readText())}}catch(e:Exception){model.importCredentials("")}}
    override fun onCreate(savedInstanceState:Bundle?){super.onCreate(savedInstanceState);WindowCompat.setDecorFitsSystemWindows(window,false);setContent{val p=remember{NativePalette(model.store.asset("palette.json"))};val body=TextStyle(fontFamily=FontFamily.SansSerif,fontSize=13.sp,lineHeight=16.sp);val typography=Typography(bodyLarge=body,bodyMedium=body,bodySmall=body.copy(fontSize=11.sp),labelLarge=body.copy(fontSize=12.sp),labelMedium=body.copy(fontSize=11.sp),labelSmall=body.copy(fontSize=10.sp),headlineSmall=body.copy(fontSize=22.sp,lineHeight=28.sp),titleLarge=body.copy(fontSize=20.sp,lineHeight=26.sp));MaterialTheme(typography=typography,colorScheme=lightColorScheme(primary=p.color("blue"),surface=Color.White,background=Color.White,onSurface=Color.Black)){CompositionLocalProvider(LocalMinimumInteractiveComponentSize provides 0.dp){Surface(color=Color.White){WorkbenchScreen(model,p){importer.launch(arrayOf("application/json","text/plain","application/octet-stream"))}}}}}}
    override fun onStart(){super.onStart();model.resume()}
    override fun onStop(){model.pause();super.onStop()}
}

class NativePalette(private val values:JSONObject){fun color(name:String)=Color(android.graphics.Color.parseColor(values.getString(name)))}
fun quoteColor(quote:Quote?,p:NativePalette):Color=when(quote?.session){"pre"->p.color("yellowText");"post"->p.color("blue");"overnight"->p.color("ink");"regular"->if(quote.previousClose==null||quote.price>=quote.previousClose)p.color("candleUp")else p.color("candleDown");else->p.color("muted")}
fun decimal(value:Double?,digits:Int=2):String=if(value==null||!value.isFinite())"—"else String.format(Locale.US,"%,.${digits}f",value)
fun compact(value:Double?):String=when{value==null||!value.isFinite()->"—";value>=1e12->"${decimal(value/1e12,1)}T";value>=1e9->"${decimal(value/1e9,1)}B";value>=1e6->"${decimal(value/1e6,1)}M";value>=1e3->"${decimal(value/1e3,1)}K";else->decimal(value,0)}
fun growth(value:Double?):String=if(value==null||!value.isFinite())"—"else if(value>=100)decimal(1+value/100,1)+"x"else decimal(value,1).removeSuffix(".0")+"%"

@Composable private fun SmallButton(label:String,selected:Boolean=false,enabled:Boolean=true,onClick:()->Unit){TextButton(onClick,enabled=enabled,contentPadding=PaddingValues(horizontal=8.dp,vertical=0.dp),modifier=Modifier.heightIn(min=36.dp),shape=RoundedCornerShape(5.dp),colors=ButtonDefaults.textButtonColors(containerColor=if(selected)Color(0xffe8f1ff)else Color.Transparent,contentColor=if(selected)MaterialTheme.colorScheme.primary else Color.Black)){Text(label,fontSize=12.sp,maxLines=1)}}

@Composable fun WorkbenchScreen(vm:Workbench,p:NativePalette,importCredentials:()->Unit){
    var showFilters by remember{mutableStateOf(false)};var showSettings by remember{mutableStateOf(false)};var hover by remember{mutableStateOf<JSONObject?>(null)}
    LaunchedEffect(vm.chart?.symbol,vm.chart?.date){hover=null}
    if(!vm.initialized){Column(Modifier.fillMaxSize().safeDrawingPadding(),verticalArrangement=Arrangement.Center,horizontalAlignment=Alignment.CenterHorizontally){if(vm.busy)CircularProgressIndicator(strokeWidth=2.dp);Spacer(Modifier.height(16.dp));Text(vm.progress,fontSize=13.sp);vm.error?.let{Text(it,color=p.color("negative"))}};return}
    Row(Modifier.fillMaxSize().safeDrawingPadding()){
        Column(Modifier.weight(.55f).fillMaxHeight()){
            ChartHeader(vm,p,hover,{vm.chart?.let{chart->chartReset?.invoke()}})
            Box(Modifier.weight(1f).fillMaxWidth()){
                val data=vm.chart
                AndroidView(factory={context->DailyWebView(context){row->hover=row}.also{chartReset={it.reset()}}},update={it.display(data);it.quote(if(vm.historical)null else vm.quotes[vm.selected+".US"])},modifier=Modifier.fillMaxSize(),onRelease={it.destroy();chartReset=null})
                if(data==null)Text(if(vm.selected.isBlank())"Select a symbol"else"Loading Daily…",Modifier.align(Alignment.Center).background(Color.White),fontSize=13.sp,color=p.color("muted"))
            }
        }
        VerticalDivider(thickness=1.dp,color=p.color("volumeLow"))
        Column(Modifier.weight(.45f).fillMaxHeight().padding(horizontal=8.dp)){
            Row(verticalAlignment=Alignment.CenterVertically,modifier=Modifier.fillMaxWidth()){
                var expanded by remember{mutableStateOf(false)}
                Box{SmallButton(vm.day+if(vm.historical)" · History"else"",onClick={expanded=true});DropdownMenu(expanded,{expanded=false}){vm.dates.forEach{date->DropdownMenuItem(text={Text(date,fontSize=13.sp)},onClick={expanded=false;vm.chooseDate(date)})}}}
                Spacer(Modifier.weight(1f));SmallButton("Refresh",enabled=!vm.busy,onClick={vm.refresh()});SmallButton("⋮",onClick={showSettings=true})
            }
            Row{listOf("discover" to "Discover","focus" to "Focus","excluded" to "Excluded").forEach{(key,name)->SmallButton(name,selected=vm.activeList==key,onClick={vm.setList(key)})};Spacer(Modifier.weight(1f));Clock(p)}
            Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically){
                SmallButton("Filters${if(vm.filters.length()>0)" · ${vm.filters.length()}"else""}",selected=vm.filters.length()>0,onClick={showFilters=true})
                Row(Modifier.weight(1f).horizontalScroll(rememberScrollState())){vm.tags.sortedBy{when(Rules.role(it)){"setup"->0;"label"->1;else->2}}.forEach{tag->SmallButton(tag.getString("name"),vm.activeTag==tag.getString("id"),onClick={vm.setTag(tag.getString("id"))})}}
            }
            var query by remember{mutableStateOf("")}
            BasicSearch(query,{query=it;vm.search(it)})
            if(vm.searchResults.isNotEmpty())LazyColumn(Modifier.heightIn(max=160.dp).border(1.dp,p.color("volumeLow"))){items(vm.searchResults){ticker->Text(ticker,Modifier.fillMaxWidth().clickable{query="";vm.chooseSearch(ticker)}.padding(10.dp),fontSize=13.sp)}}
            val rows=vm.rows();val sections=buildList<Pair<String,String>>{
                if(rows.any{it.pinned})add("pinned" to "Pinned")
                if(vm.activeList=="excluded")addAll(listOf("earnings" to "In 14 Days","broken" to "Broken","extended" to "Extended","under50" to "Under-50","hidden" to "Hidden"))
                else {addAll(vm.tags.filter{Rules.role(it)=="setup"}.map{it.getString("id") to it.getString("name")});add("unclassified" to "Unclassified")}
            }
            Row(Modifier.fillMaxWidth().height(28.dp).border(BorderStroke(.5.dp,p.color("volumeLow"))),verticalAlignment=Alignment.CenterVertically){
                Cell("Symbol",.18f);Cell("Close",.12f);Cell("Latest",.13f);Cell("ADR",.10f);Cell("MDV",.13f)
                var sortOpen by remember{mutableStateOf(false)}
                Box(Modifier.weight(.21f)){Text(if(vm.sort=="default")"RFL 1 / 3 / 6m"else vm.sort.uppercase()+" ↓",Modifier.fillMaxWidth().clickable{sortOpen=true},fontSize=10.sp,textAlign=TextAlign.Center);DropdownMenu(sortOpen,{sortOpen=false}){listOf("default","rfl1m","rfl3m","rfl6m").forEach{value->DropdownMenuItem({Text(value.uppercase())},{sortOpen=false;vm.chooseSort(value)})}}}
                Cell("Tags",.07f);Cell("",.06f)
            }
            val collapsed=remember(vm.activeList){mutableStateMapOf<String,Boolean>()}
            LazyColumn(Modifier.weight(1f)){
                sections.forEach{(id,label)->val members=rows.filter{if(id=="pinned")it.pinned else !it.pinned&&it.section==id}
                    if(members.isNotEmpty()||(vm.activeList!="excluded"&&id!="pinned")){
                        item(key="section:$id"){Row(Modifier.fillMaxWidth().clickable{collapsed[id]=collapsed[id]!=true}.padding(top=10.dp,bottom=5.dp),verticalAlignment=Alignment.CenterVertically){Text((if(collapsed[id]==true)"▸ "else"▾ ")+label,fontSize=11.sp,color=p.color("tagNeutral"));Text("  ${members.size}",fontSize=10.sp,color=p.color("muted"))}}
                        if(collapsed[id]!=true)items(members,key={it.ticker}){row->SymbolRow(row,vm,p)}
                    }
                }
                if(rows.isEmpty())item{Text("No matching symbols",Modifier.padding(16.dp),fontSize=12.sp,color=p.color("muted"))}
            }
            if(vm.busy){LinearProgressIndicator(Modifier.fillMaxWidth().height(2.dp));Text(vm.progress,Modifier.padding(vertical=4.dp),fontSize=10.sp,maxLines=1,overflow=TextOverflow.Ellipsis)}
            Row(Modifier.fillMaxWidth().padding(vertical=5.dp),verticalAlignment=Alignment.CenterVertically){Text(vm.quoteStatus,Modifier.weight(1f),fontSize=10.sp,color=p.color("tagNeutral"),maxLines=1);if(!vm.authorized)SmallButton("Import credentials",onClick=importCredentials)}
            if(vm.infoStatus.isNotEmpty())Text(vm.infoStatus,Modifier.padding(bottom=4.dp),fontSize=10.sp,color=p.color("muted"),maxLines=1,overflow=TextOverflow.Ellipsis)
        }
    }
    vm.error?.let{message->AlertDialog(onDismissRequest={vm.clearError()},title={Text("Market Monitor")},text={Text(message)},confirmButton={TextButton({vm.clearError()}){Text("OK")}})}
    if(showFilters)FilterDialog(vm){showFilters=false}
    if(showSettings)AlertDialog(onDismissRequest={showSettings=false},title={Text("Data")},text={Column{Text("Daily · Massive\nQuotes · Longbridge account 2\nIndependent on-device data\nPrototype 0.1.0",fontSize=13.sp);Spacer(Modifier.height(12.dp));SmallButton("Import credentials",onClick={showSettings=false;importCredentials()});SmallButton("Refresh Additional Info",onClick={showSettings=false;vm.refreshAdditional()});SmallButton("Update symbol directory",enabled=!vm.busy,onClick={showSettings=false;vm.updateDirectory()});Text("Lightweight Charts™ by TradingView\nApache 2.0 · LICENSE and NOTICE bundled",fontSize=11.sp,color=p.color("tagNeutral"))}},confirmButton={TextButton({showSettings=false}){Text("Close")}})
}

// One active chart belongs to the single Activity; the callback is cleared when its WebView is released.
private var chartReset:(()->Unit)?=null

@Composable private fun RowScope.Cell(text:String,weight:Float,color:Color=Color.Black,bold:Boolean=false){Text(text,Modifier.weight(weight).padding(horizontal=2.dp),fontSize=11.sp,color=color,fontWeight=if(bold)FontWeight.SemiBold else FontWeight.Normal,maxLines=1,overflow=TextOverflow.Ellipsis,textAlign=if(weight==.18f)TextAlign.Start else TextAlign.End)}
@Composable private fun BasicSearch(value:String,onValue:(String)->Unit){androidx.compose.foundation.text.BasicTextField(value,onValue,modifier=Modifier.fillMaxWidth().height(34.dp).padding(vertical=6.dp),singleLine=true,textStyle=androidx.compose.ui.text.TextStyle(fontSize=13.sp,color=Color.Black),decorationBox={inner->Box{if(value.isEmpty())Text("Search ticker",fontSize=12.sp,color=Color(0xff9ca3af));inner()}})}
@Composable private fun Clock(p:NativePalette){var time by remember{mutableStateOf(ZonedDateTime.now(ET))};LaunchedEffect(Unit){while(true){kotlinx.coroutines.delay(1000);time=ZonedDateTime.now(ET)}};Text(time.format(java.time.format.DateTimeFormatter.ofPattern("HH:mm:ss"))+" ET",fontSize=10.sp,color=p.color("tagNeutral"))}

@Composable private fun SymbolRow(row:ListRow,vm:Workbench,p:NativePalette){
    val quote=if(vm.historical)null else vm.quotes[row.ticker+".US"];val chosen=vm.selected==row.ticker;var menu by remember{mutableStateOf(false)}
    val selectedBorder=if(chosen)p.color("ink")else Color.Transparent
    Row(Modifier.fillMaxWidth().height(42.dp).border(.75.dp,selectedBorder,RoundedCornerShape(21.dp)).clickable{vm.select(row.ticker)}.padding(horizontal=7.dp),verticalAlignment=Alignment.CenterVertically){
        Cell(row.ticker,.18f,bold=true);Cell(decimal(row.feature.number("close")),.12f)
        Cell(decimal(quote?.price),.13f,quoteColor(quote,p))
        Cell(row.feature.number("adr20")?.let{decimal(it,1)+"%"}?:"—",.10f)
        Cell(compact(row.feature.number("mdv20")),.13f)
        Row(Modifier.weight(.21f)){listOf("rfl1m","rfl3m","rfl6m").forEach{key->Text(growth(row.feature.number(key)),Modifier.weight(1f),fontSize=10.sp,textAlign=TextAlign.End,maxLines=1)}}
        Row(Modifier.weight(.07f),horizontalArrangement=Arrangement.End){row.tags.take(2).forEach{id->vm.tags.firstOrNull{it.getString("id")==id}?.let{TagGlyph(it,Modifier.width(14.dp).height(11.dp))}}}
        Box(Modifier.weight(.06f)){Text("⋮",Modifier.fillMaxWidth().clickable(enabled=!vm.historical){menu=true}.padding(vertical=9.dp),textAlign=TextAlign.Center,color=p.color("tagNeutral"),fontSize=16.sp);DropdownMenu(menu,{menu=false}){
            DropdownMenuItem({Text(if(row.pinned)"Unpin"else"Pin")},{menu=false;vm.action(row.ticker,"pin")})
            if(row.status!="focus")DropdownMenuItem({Text("Add to Focus")},{menu=false;vm.action(row.ticker,"focus")})
            if(row.section=="hidden")DropdownMenuItem({Text("Release")},{menu=false;vm.action(row.ticker,"release")})
            else DropdownMenuItem({Text("Move to Hidden")},{menu=false;vm.action(row.ticker,"hide")})
            if(row.status=="focus")DropdownMenuItem({Text("Move to Discover")},{menu=false;vm.action(row.ticker,"release-focus")})
        }}
    }
}

@Composable private fun TagGlyph(tag:JSONObject,modifier:Modifier){
    val appearance=tag.optJSONObject("appearance");val id=appearance?.optString("icon","label")?:"label"
    val color=android.graphics.Color.parseColor(appearance?.optString("color","#64748b")?:"#64748b")
    val paths=when(id){"surf"->listOf("M3 8L10 5L16 7L24 3L33 4","M3 16C15 16 21 11 33 10");"bounce"->listOf("M3 2L15 16L31 2M24 2H31V9","M3 16Q18 16 33 13");"extended"->listOf("M3 18C25 18 32 18 33 2");"broken"->listOf("M3 2L12 3L20 13L32 17M27 17H32V12","M3 7H33");"prior-run"->listOf("M3 16H11V12H19V7H27V2H33");"orderly-pullback"->listOf("M3 3H11V7H19V11H27V15H33");"under50"->listOf("M2 4Q6 0 10 4T18 4T26 4T34 4","M15 12Q18 9 21 12M2 12H5M31 12H34");else->listOf("M3 3H22L33 10L22 17H3Z")}
    val paint=remember(color){android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply{this.color=color;style=android.graphics.Paint.Style.STROKE;strokeWidth=1.8f}}
    Canvas(modifier){drawIntoCanvas{canvas->val native=canvas.nativeCanvas;native.save();native.scale(size.width/36,size.height/20);paths.forEach{path->androidx.core.graphics.PathParser.createPathFromPathData(path)?.let{native.drawPath(it,paint)}};if(id=="under50"){native.drawRoundRect(5f,10f,15f,18f,3f,3f,paint);native.drawRoundRect(21f,10f,31f,18f,3f,3f,paint)};if(id=="label")native.drawCircle(24f,10f,1.5f,paint);native.restore()}}
}

@Composable private fun ChartHeader(vm:Workbench,p:NativePalette,hover:JSONObject?,reset:()->Unit){
    val company=vm.info;val row=hover?:vm.chart?.rows?.lastOrNull()?.toJson();val feature=vm.features[vm.selected];val quote=if(vm.historical)null else vm.quotes[vm.selected+".US"]
    Column(Modifier.fillMaxWidth().padding(horizontal=12.dp).height(132.dp)){
        Row(Modifier.height(36.dp),verticalAlignment=Alignment.CenterVertically){Text(vm.selected,fontSize=24.sp,fontWeight=FontWeight.Bold);Text(company.nullable("company_name")?:"",Modifier.weight(1f).padding(start=8.dp),fontSize=13.sp,color=p.color("tagNeutral"),maxLines=1,overflow=TextOverflow.Ellipsis);Text(if(vm.historical)""else decimal(quote?.price),fontSize=23.sp,color=quoteColor(quote,p));SmallButton("↦",onClick=reset)}
        val categories=listOfNotNull(company.nullable("sector"),company.nullable("industry")).map{it.substringBefore(':').replace(Regex("\\([^)]*\\)"),"").trim().replace(Regex("\\s+")," ")}.filter{it.isNotEmpty()}.distinctBy{it.lowercase()}
        Row{Text(categories.joinToString(" · "),Modifier.weight(1f),fontSize=11.sp,color=p.color("tagNeutral"),maxLines=1,overflow=TextOverflow.Ellipsis);Text(company.nullable("market_cap")?.toDoubleOrNull()?.let{"Market Cap "+compact(it)}?:"",fontSize=11.sp)}
        Row(Modifier.padding(top=4.dp)){Text("ADR ${decimal(feature?.number("adr20"),1)}%   MDV ${compact(feature?.number("mdv20"))}",fontSize=13.sp,modifier=Modifier.weight(1f));Text(earningsText(company),fontSize=10.sp,color=p.color("tagNeutral"),maxLines=1)}
        Row(Modifier.padding(top=5.dp,bottom=4.dp),horizontalArrangement=Arrangement.spacedBy(10.dp)){Text("━ EMA 10",fontSize=10.sp,color=p.color("blue"));Text("━ EMA 20",fontSize=10.sp,color=p.color("yellow"));Text("━ SMA 50",fontSize=10.sp,color=p.color("red"));Spacer(Modifier.weight(1f));Text(hover?.nullable("day")?:vm.chart?.rows?.lastOrNull()?.date?.toString()?:"",fontSize=10.sp,color=p.color("tagNeutral"))}
        HorizontalDivider(color=Color.Black,thickness=.5.dp)
        Text(row?.let{"O ${decimal(it.number("open"))}   H ${decimal(it.number("high"))}   L ${decimal(it.number("low"))}   C ${decimal(it.number("close"))}   ${decimal(it.number("low")?.let{low->(it.getDouble("high")-low)/low*100},1)}%"}?:"",fontSize=11.sp,maxLines=1,modifier=Modifier.padding(top=5.dp))
    }
}
private fun earningsText(info:JSONObject):String{val today=todayET();val last=info.nullable("last_earnings")?.let{LocalDate.parse(it)};val next=info.nullable("next_earnings")?.let{LocalDate.parse(it)};return if(last!=null&&ChronoUnit.DAYS.between(last,today) in 0..7){val n=ChronoUnit.DAYS.between(last,today);if(n==0L)"Reported today"else"Reported $n days ago"}else if(next!=null){val n=ChronoUnit.DAYS.between(today,next);if(n==0L)"Earnings today · est."else"Earnings in $n days · est."}else if(last!=null)"Reported ${ChronoUnit.DAYS.between(last,today)} days ago"else""}

@Composable private fun FilterDialog(vm:Workbench,dismiss:()->Unit){
    var draft by remember{mutableStateOf(vm.filters.copy())};var validation by remember{mutableStateOf("")}
    val catalog=remember{JSONArray(vm.store.context.assets.open("filter-catalog.json").bufferedReader().use{it.readText()}).objects()}
    AlertDialog(onDismissRequest=dismiss,title={Text("Filters")},text={Column(Modifier.heightIn(max=420.dp).verticalScroll(rememberScrollState())){
        catalog.forEach{field->val key=field.getString("key");val rule=draft.optJSONObject(key)?:JSONObject()
            Text(field.getString("label")+field.nullable("unit")?.let{" · $it"}.orEmpty(),fontSize=12.sp,modifier=Modifier.padding(top=10.dp))
            if(field.getString("type")=="choice")Row(Modifier.horizontalScroll(rememberScrollState())){field.objects("options").forEach{option->val selected=rule.strings("values");val value=option.getString("value");SmallButton(option.getString("label"),value in selected,onClick={val next=selected.toMutableList();if(value in next)next.remove(value)else next.add(value);draft=draft.copy().apply{if(next.isEmpty())remove(key)else put(key,json("values" to array(next)))}})}}
            else Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){
                listOf("min" to "Minimum","max" to "Maximum").forEach{(bound,label)->var input by remember(key,bound){mutableStateOf(rule.number(bound)?.toString()?:"")};OutlinedTextField(input,{value->input=value;val number=value.toDoubleOrNull();validation=if(value.isNotBlank()&&(number==null||!number.isFinite()))"Enter a finite number"else"";if(value.isBlank()||number!=null&&number.isFinite()){draft=draft.copy().apply{val updated=optJSONObject(key)?.copy()?:JSONObject();if(value.isBlank())updated.remove(bound)else updated.put(bound,number);if(!updated.has("min")&&!updated.has("max"))remove(key)else put(key,updated)}}},label={Text(label,fontSize=11.sp)},singleLine=true,modifier=Modifier.weight(1f))}
            }
        };if(validation.isNotEmpty())Text(validation,color=MaterialTheme.colorScheme.error)
    }},confirmButton={TextButton({if(validation.isEmpty()){vm.applyFilters(draft);dismiss()}},enabled=validation.isEmpty()){Text("Apply")}},dismissButton={Row{TextButton({vm.applyFilters(JSONObject());dismiss()}){Text("Clear")};TextButton(dismiss){Text("Cancel")}}})
}

@Suppress("SetJavaScriptEnabled")
class DailyWebView(context:android.content.Context,private val hover:(JSONObject?)->Unit):WebView(context){
    private var ready=false;private var pending:ChartData?=null;private var identity="";private var latestQuote:Quote?=null
    init{setBackgroundColor(android.graphics.Color.WHITE);settings.javaScriptEnabled=true;settings.allowFileAccess=false;settings.allowContentAccess=false;settings.domStorageEnabled=false
        addJavascriptInterface(object{@JavascriptInterface fun hover(value:String){post{val row=if(value=="null")null else JSONObject(value);if(row==null||row.optString("symbol")==pending?.symbol?.removeSuffix(".US")&&row.optString("date")==pending?.date)hover(row)}}},"NativeChart")
        webViewClient=object:WebViewClient(){override fun shouldOverrideUrlLoading(view:WebView,request:WebResourceRequest)=true
            override fun shouldInterceptRequest(view:WebView,request:WebResourceRequest):WebResourceResponse {val name=request.url.path?.removePrefix("/")?:"";return if(request.url.host=="appassets.androidplatform.net"&&name in listOf("chart.html","chart.js","lightweight-charts.standalone.production.js","palette.json"))WebResourceResponse(if(name.endsWith("html"))"text/html"else if(name.endsWith("json"))"application/json"else"application/javascript","UTF-8",context.assets.open(name))else WebResourceResponse("text/plain","UTF-8",404,"Not found",emptyMap(),"".byteInputStream())}
            override fun onPageFinished(view:WebView,url:String){ready=true;resizeChart();display(pending);quote(latestQuote)} }
        loadUrl("https://appassets.androidplatform.net/chart.html")
    }
    override fun onSizeChanged(w:Int,h:Int,oldw:Int,oldh:Int){super.onSizeChanged(w,h,oldw,oldh);resizeChart()}
    private fun resizeChart(){if(ready&&width>0&&height>0){val density=resources.displayMetrics.density;evaluateJavascript("window.resizeDaily(${width/density},${height/density})",null)}}
    fun display(data:ChartData?){val changed=pending?.symbol!=data?.symbol||pending?.date!=data?.date;pending=data;if(changed)latestQuote=null;if(!ready)return;val key=data?.let{"${it.symbol}:${it.date}:${it.payload.hashCode()}"}?:"empty";if(identity==key)return;identity=key;evaluateJavascript("window.loadDaily(${data?.payload?:"null"})",null);quote(latestQuote)}
    fun quote(value:Quote?){latestQuote=value;if(ready)evaluateJavascript("window.updateQuote(${value?.let{json("price" to it.price,"session" to it.session,"previousClose" to it.previousClose)}?:"null"})",null)}
    fun reset(){if(ready)evaluateJavascript("window.resetDaily()",null)}
}
