package com.cyno.marketmonitor

import org.json.JSONArray
import org.json.JSONObject
import java.time.*

val ET: ZoneId = ZoneId.of("America/New_York")
fun todayET(): LocalDate = LocalDate.now(ET)
fun JSONObject.objects(key: String): List<JSONObject> = optJSONArray(key)?.objects() ?: emptyList()
fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
fun JSONArray.strings(): List<String> = (0 until length()).map { getString(it) }
fun JSONObject.strings(key: String): List<String> = optJSONArray(key)?.strings() ?: emptyList()
fun JSONObject.copy(): JSONObject = JSONObject(toString())
fun JSONObject.entries(): List<Pair<String, Any>> = keys().asSequence().map { it to get(it) }.toList()
fun JSONObject.number(key: String): Double? = (opt(key) as? Number)?.toDouble()?.takeIf { it.isFinite() }
fun JSONObject.nullable(key: String): String? = if (isNull(key)) null else optString(key).takeIf { it.isNotEmpty() }
fun json(vararg values: Pair<String, Any?>): JSONObject = JSONObject().apply { values.forEach { (k,v) -> put(k,v ?: JSONObject.NULL) } }
fun array(values: Collection<*>): JSONArray = JSONArray(values)

data class DailyBar(val symbol: String, val time: Long, val open: Double, val high: Double, val low: Double,
    val close: Double, val volume: Long, val turnover: Double?) {
    val date: LocalDate get() = Instant.ofEpochSecond(time).atZone(ET).toLocalDate()
    fun toJson(): JSONObject = json("symbol" to symbol, "time" to time, "open" to open, "high" to high,
        "low" to low, "close" to close, "volume" to volume, "turnover" to turnover)
}
data class Quote(val price: Double, val timestamp: Long, val session: String, val previousClose: Double? = null)
data class ListRow(val ticker: String, val status: String, val section: String, val tags: List<String>,
    val feature: JSONObject, val pinned: Boolean)
data class ChartData(val symbol: String, val date: String, val rows: List<DailyBar>, val payload: String)

class SessionCalendar(data: JSONObject) {
    val sessions: Map<LocalDate, Pair<Long,Long>> = data.entries().associate { (date,value) ->
        val times = value as JSONArray
        LocalDate.parse(date) to (times.getLong(0) to times.getLong(1))
    }.toSortedMap()
    fun days(start: LocalDate, end: LocalDate) = sessions.keys.filter { it >= start && it <= end }
    fun previous(day: LocalDate, count: Int = 5) = sessions.keys.filter { it < day }.takeLast(count)
    fun stamp(day: LocalDate): Long = day.atStartOfDay(ET).toEpochSecond()
    fun target(now: ZonedDateTime = ZonedDateTime.now(ET)): LocalDate {
        val end = now.toLocalDate().minusDays(if (now.hour < 18) 1 else 0)
        require(end <= sessions.keys.last()) { "Trading calendar expired; update the APK" }
        return days(end.minusDays(15),end).lastOrNull() ?: error("No completed exchange session")
    }
}

object Rules {
    val negativeRoles = listOf("earnings", "broken", "extended", "under50")
    fun role(tag: JSONObject): String = tag.nullable("role") ?: when(tag.optString("name").lowercase()) {
        "extended" -> "extended"; "broken" -> "broken"; "under-50" -> "under50"; else -> "setup"
    }
    fun matches(row: JSONObject, filters: JSONObject): Boolean = filters.entries().all { (key, obj) ->
        val rule = obj as JSONObject
        if (!rule.has("min") && !rule.has("max") && !rule.has("values")) true
        else if (row.isNull(key)) false
        else if (rule.has("values")) (0 until rule.getJSONArray("values").length()).any { rule.getJSONArray("values").get(it) == row.get(key) }
        else row.number(key)?.let { value ->
            (!rule.has("min") || value >= rule.getDouble("min")) &&
                (!rule.has("max") || if(rule.optBoolean("maxExclusive")) value < rule.getDouble("max") else value <= rule.getDouble("max"))
        } ?: false
    }
    fun matched(row: JSONObject, definitions: List<JSONObject>, manual: List<String> = emptyList()): List<JSONObject> = definitions.filter { tag ->
        val filters = tag.optJSONObject("filters") ?: JSONObject()
        (tag.getString("id") in manual && role(tag) in listOf("setup","label")) ||
            (filters.entries().any { (_,v) -> (v as JSONObject).let { it.has("min") || it.has("max") || it.has("values") } } && matches(row, filters))
    }
    fun hidden(state: JSONObject, day: LocalDate): Boolean = state.optString("status") == "excluded" && state.optString("section") == "hidden" &&
        java.time.temporal.ChronoUnit.DAYS.between(LocalDate.parse(state.optString("excluded_at",state.optString("status_at",day.toString()))),day) < 7
    fun empty(): JSONObject = json("version" to 3, "carried" to JSONArray(), "statuses" to JSONObject(), "pinned" to JSONArray(),
        "orders" to json("discover" to JSONArray(), "focus" to JSONArray(), "excluded" to JSONArray()))
    fun reset(workspace: JSONObject, day: LocalDate, inherit: Boolean = false): JSONObject {
        val result = workspace.copy(); val states = result.getJSONObject("statuses")
        states.entries().forEach { (ticker,obj) ->
            val state = obj as JSONObject
            if(state.optString("status") != "focus" && !hidden(state,day)) states.remove(ticker)
            else {
                state.put("tags",JSONArray())
                if(state.optString("status") == "focus") state.put("section","unclassified")
                listOf("manual_focus_date","manual_discover_date","manual_section_date","manual_tags_date","manual_tags").forEach { state.remove(it) }
            }
        }
        result.put("pinned",JSONArray())
        if(inherit) result.put("carried",array(states.entries().filter { (it.second as JSONObject).optString("status")=="focus" }.map { it.first }.sorted()))
        return result
    }
    fun classify(workspace: JSONObject, features: Map<String,JSONObject>, tags: List<JSONObject>, day: LocalDate): JSONObject {
        val result = workspace.copy(); val previous = result.getJSONObject("statuses").copy()
        val states = result.getJSONObject("statuses"); val candidates = features.filterValues { it.optBoolean("candidate") }.keys
        val manualDiscover = previous.entries().filter { (_,v) -> (v as JSONObject).let { it.optString("status")=="discover" && it.optString("manual_discover_date")==day.toString() } }.map { it.first }.toSet()
        val scope = candidates + manualDiscover + previous.entries().filter { (_,v) -> (v as JSONObject).let { it.optString("status")=="focus" || hidden(it,day) } }.map { it.first }
        states.keys().asSequence().toList().filter { it !in scope }.forEach { states.remove(it) }
        scope.sorted().forEach { ticker ->
            val state = states.optJSONObject(ticker) ?: json("status" to "discover","section" to "unclassified","status_at" to day.toString()).also { states.put(ticker,it) }
            if(hidden(state,day)) { state.put("tags",JSONArray()); state.remove("manual_tags"); state.remove("manual_tags_date"); return@forEach }
            if(state.optString("section")=="hidden") { state.put("status","discover"); state.put("section","unclassified"); state.remove("excluded_at") }
            val manual = if(state.optString("manual_tags_date")==day.toString()) state.strings("manual_tags") else emptyList()
            if(manual.isEmpty()) {state.remove("manual_tags");state.remove("manual_tags_date")}
            val matched = matched(features[ticker] ?: JSONObject(),tags,manual)
            state.put("tags",array(matched.map { it.getString("id") }))
            val setup = matched.firstOrNull { role(it)=="setup" }?.getString("id") ?: "unclassified"
            val negative = negativeRoles.firstOrNull { role -> matched.any { role(it)==role } }
            val manualFocus = state.optString("status")=="focus" && state.optString("manual_focus_date")==day.toString()
            if(negative!=null && !manualFocus && ticker !in manualDiscover) {state.put("status","excluded");state.put("section",negative);state.remove("excluded_at");state.remove("manual_section_date")}
            else if(state.optString("status")=="excluded") {state.put("status","discover");state.put("section",setup);state.remove("manual_section_date");state.remove("manual_focus_date")}
            else if(state.optString("manual_section_date")!=day.toString() || tags.none { it.getString("id")==state.optString("section") && role(it)=="setup" }) state.put("section",setup)
            if(state.optString("status")!="focus" && ticker !in candidates+manualDiscover) states.remove(ticker)
        }
        val orders = result.optJSONObject("orders") ?: JSONObject()
        listOf("discover","focus","excluded").forEach { status ->
            val members = states.entries().filter { (it.second as JSONObject).optString("status")==status }.map { it.first }.toSet()
            val unchanged = orders.strings(status).filter { ticker -> ticker in members && previous.optJSONObject(ticker)?.let { it.optString("status")==status && it.optString("section")==states.getJSONObject(ticker).optString("section") } == true }
            orders.put(status,array((members-unchanged.toSet()).sorted()+unchanged))
        }
        result.put("orders",orders)
        result.put("pinned",array(result.strings("pinned").filter { ticker -> states.has(ticker) && previous.optJSONObject(ticker)?.optString("status",states.getJSONObject(ticker).optString("status"))==states.getJSONObject(ticker).optString("status") }))
        return result
    }
    fun persistent(workspace: JSONObject): JSONObject = workspace.copy().apply {
        val states=getJSONObject("statuses")
        states.entries().filter { (_,v) -> (v as JSONObject).let { it.optString("status")=="excluded" && it.optString("section")!="hidden" } }.forEach { states.remove(it.first) }
        val orders=getJSONObject("orders")
        listOf("discover","focus","excluded").forEach { status -> orders.put(status,array(orders.strings(status).filter { states.has(it) })) }
    }
}
