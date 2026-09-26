package com.bofstudios.moneytree.ai

import com.bofstudios.moneytree.engine.Explainer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Turns a decision the rules already made into two plain sentences.
 *
 * The model never decides anything: it is handed the facts of a trade that has
 * already been placed and asked to explain them. It is told not to predict and
 * not to advise, and it only sees numbers the engine measured.
 */
class GroqExplainer(
    private val apiKey: String,
    private val model: String = "openai/gpt-oss-120b",
    private val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS).readTimeout(45, TimeUnit.SECONDS).build(),
) : Explainer {

    override suspend fun explain(facts: String, turkish: Boolean): String? = withContext(Dispatchers.IO) {
        val system = buildString {
            append("You explain a trading bot's decision to its owner, who may be new to markets. ")
            append("Use only the facts given. Two or three short sentences. ")
            append("Explain what the rule saw and how the stop-loss limits the loss. ")
            append("Never predict prices, never say it will go up, never give investment advice. ")
            if (turkish) append("Reply in natural Turkish.")
        }
        val body = JSONObject()
            .put("model", model)
            // gpt-oss reasons before it answers; a tight budget returns nothing visible.
            .put("max_tokens", 700)
            .put("messages", JSONArray()
                .put(JSONObject().put("role", "system").put("content", system))
                .put(JSONObject().put("role", "user").put("content", facts)))
        val request = Request.Builder()
            .url("https://api.groq.com/openai/v1/chat/completions")
            .header("Authorization", "Bearer $apiKey")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()
        http.newCall(request).execute().use { response ->
            if (!response.isSuccessful) return@withContext null
            val choices = JSONObject(response.body?.string().orEmpty()).optJSONArray("choices")
            choices?.optJSONObject(0)?.optJSONObject("message")?.optString("content")
                ?.trim()?.takeIf { it.isNotEmpty() }
        }
    }
}
