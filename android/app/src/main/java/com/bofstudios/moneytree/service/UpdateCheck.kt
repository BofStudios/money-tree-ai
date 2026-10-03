package com.bofstudios.moneytree.service

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import java.util.concurrent.TimeUnit

/**
 * Asks GitHub (public API, no key) whether a newer Android release is out, so
 * an update reaches the phone without anyone having to say so. It only
 * offers the download; Android always asks the owner before installing.
 */
object UpdateCheck {
    private const val RELEASES = "https://api.github.com/repos/BofStudios/money-tree-ai/releases?per_page=20"

    /** The newest android release above [current]: its version and APK link. */
    suspend fun newer(current: String): Pair<String, String>? = withContext(Dispatchers.IO) {
        runCatching {
            val http = OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS).build()
            val request = Request.Builder().url(RELEASES)
                .header("User-Agent", "MoneyTree-App").header("Accept", "application/vnd.github+json").build()
            http.newCall(request).execute().use { r ->
                if (!r.isSuccessful) return@use null
                val arr = JSONArray(r.body?.string().orEmpty())
                (0 until arr.length()).map { arr.getJSONObject(it) }
                    .filter { !it.optBoolean("draft") && !it.optBoolean("prerelease") && it.optString("tag_name").startsWith("android-v") }
                    .map { rel ->
                        val version = rel.optString("tag_name").removePrefix("android-v")
                        val assets = rel.optJSONArray("assets") ?: JSONArray()
                        val apk = (0 until assets.length()).map { assets.getJSONObject(it) }
                            .firstOrNull { it.optString("name").endsWith(".apk") }?.optString("browser_download_url")
                        version to (apk ?: rel.optString("html_url"))
                    }
                    .filter { isNewer(it.first, current) }
                    .maxWithOrNull { a, b -> compare(a.first, b.first) }
            }
        }.getOrNull()
    }

    fun isNewer(candidate: String, current: String) = compare(candidate, current) > 0

    private fun compare(a: String, b: String): Int {
        val x = a.split(".").map { it.toIntOrNull() ?: 0 }
        val y = b.split(".").map { it.toIntOrNull() ?: 0 }
        for (i in 0 until maxOf(x.size, y.size)) {
            val c = (x.getOrElse(i) { 0 }).compareTo(y.getOrElse(i) { 0 })
            if (c != 0) return c
        }
        return 0
    }
}
