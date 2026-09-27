package com.bofstudios.moneytree.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * API keys, encrypted with a key that never leaves the phone's Keystore.
 *
 * The AES key is generated inside Android Keystore and cannot be exported, so
 * the preferences file on disk only ever holds ciphertext. Backups are switched
 * off in the manifest as well, so the file does not travel either.
 */
class SecureStore(context: Context) {
    private val prefs = context.getSharedPreferences("secure", Context.MODE_PRIVATE)

    fun put(name: String, value: String?) {
        if (value.isNullOrBlank()) {
            prefs.edit().remove(name).apply()
            return
        }
        val cipher = Cipher.getInstance(TRANSFORM)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val sealed = cipher.iv + cipher.doFinal(value.trim().toByteArray(Charsets.UTF_8))
        prefs.edit().putString(name, Base64.encodeToString(sealed, Base64.NO_WRAP)).apply()
    }

    fun get(name: String): String? {
        val stored = prefs.getString(name, null) ?: return null
        return try {
            val bytes = Base64.decode(stored, Base64.NO_WRAP)
            val cipher = Cipher.getInstance(TRANSFORM)
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes, 0, IV_BYTES))
            String(cipher.doFinal(bytes, IV_BYTES, bytes.size - IV_BYTES), Charsets.UTF_8)
        } catch (e: Exception) {
            // A Keystore reset (new screen lock on some devices) makes old
            // ciphertext unreadable. Treat it as "not set" and ask again.
            null
        }
    }

    fun has(name: String): Boolean = get(name) != null

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return generator.generateKey()
    }

    companion object {
        private const val ALIAS = "moneytree-secrets"
        private const val TRANSFORM = "AES/GCM/NoPadding"
        private const val IV_BYTES = 12

        const val PAPER_KEY = "alpaca_paper_key"
        const val PAPER_SECRET = "alpaca_paper_secret"
        const val LIVE_KEY = "alpaca_live_key"
        const val LIVE_SECRET = "alpaca_live_secret"
        const val GROQ_KEY = "groq_key"
    }
}
