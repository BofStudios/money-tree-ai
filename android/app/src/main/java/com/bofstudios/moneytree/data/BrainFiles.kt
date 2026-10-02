package com.bofstudios.moneytree.data

import com.bofstudios.moneytree.engine.BrainStore
import java.io.File

/**
 * The brain's memory as small JSON files in the app's private storage:
 * company reports, the news it kept, the signals it followed and what it
 * learned. Nothing secret — keys stay in [SecureStore]. Each write goes to a
 * temporary file first, so a crash mid-write never leaves half a document.
 */
class BrainFiles(private val dir: File) : BrainStore {
    init { dir.mkdirs() }

    override fun read(name: String): String? = synchronized(this) {
        runCatching { file(name).takeIf { it.exists() }?.readText() }.getOrNull()
    }

    override fun write(name: String, text: String) = synchronized(this) {
        runCatching {
            val target = file(name)
            val tmp = File(dir, target.name + ".tmp")
            tmp.writeText(text)
            if (!tmp.renameTo(target)) { target.delete(); tmp.renameTo(target) }
        }
        Unit
    }

    /** Wipes what it learned (the owner's "forget" button); reports and news stay. */
    fun forgetLearning() = synchronized(this) {
        listOf("samples", "shadows", "lessons", "plans").forEach { file(it).delete() }
    }

    private fun file(name: String) = File(dir, name.replace(Regex("[^A-Za-z0-9_.-]"), "_") + ".json")
}
