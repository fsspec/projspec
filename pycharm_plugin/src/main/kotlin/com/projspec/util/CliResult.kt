package com.projspec.util

/**
 * Result returned from a CLI invocation.
 *
 * [Success.stdout] carries the captured standard output.
 * [Failure.message] is either stderr or a short explanation (timeout, launch
 * failure, non-zero exit code).  [Failure.exitCode] preserves the original
 * process exit code, or -1 when the process could not be started.
 */
sealed class CliResult {
    data class Success(val stdout: String) : CliResult()
    data class Failure(val message: String, val exitCode: Int = -1) : CliResult()
}
