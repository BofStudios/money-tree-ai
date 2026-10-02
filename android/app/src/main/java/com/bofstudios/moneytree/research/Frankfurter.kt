package com.bofstudios.moneytree.research

import com.bofstudios.moneytree.engine.FxSource
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * The European Central Bank's daily reference rates, through the free
 * Frankfurter API (no key). Needed because ASML, SAP and Unilever report in
 * euros and Novo Nordisk in kroner, while their New York shares trade in
 * dollars.
 */
class Frankfurter(
    private val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS).readTimeout(20, TimeUnit.SECONDS).build(),
) : FxSource {
    override suspend fun usdPer(currency: String): Double? = withContext(Dispatchers.IO) {
        if (currency == "USD") return@withContext 1.0
        val request = Request.Builder()
            .url("https://api.frankfurter.dev/v1/latest?base=USD&symbols=${currency.uppercase()}")
            .header("User-Agent", SecEdgar.USER_AGENT)
            .build()
        runCatching {
            http.newCall(request).execute().use { r ->
                if (!r.isSuccessful) return@use null
                val perUsd = JSONObject(r.body?.string().orEmpty()).optJSONObject("rates")?.optDouble(currency.uppercase())
                perUsd?.takeIf { it > 0 && !it.isNaN() }?.let { 1.0 / it }
            }
        }.getOrNull()
    }
}
