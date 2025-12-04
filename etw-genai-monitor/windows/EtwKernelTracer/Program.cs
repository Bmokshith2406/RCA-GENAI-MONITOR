using System;
using System.Text.Json;
using System.Collections;
using System.Collections.Generic;
using System.Net;

using Microsoft.Diagnostics.Tracing;
using Microsoft.Diagnostics.Tracing.Parsers;
using Microsoft.Diagnostics.Tracing.Session;

class Program
{
    static void Main(string[] args)
    {
        using var session = new TraceEventSession(
            $"GenAI-Kernel-{Guid.NewGuid()}"
        );

        session.StopOnDispose = true;

        Console.CancelKeyPress += delegate
        {
            session.Stop();
        };

        // --------------------------------------------------
        // KERNEL PROVIDERS
        // --------------------------------------------------

        session.EnableKernelProvider(
            KernelTraceEventParser.Keywords.Process |
            KernelTraceEventParser.Keywords.Thread |
            KernelTraceEventParser.Keywords.NetworkTCPIP |
            KernelTraceEventParser.Keywords.FileIO |
            KernelTraceEventParser.Keywords.ContextSwitch |
            KernelTraceEventParser.Keywords.Profile |   // CPU sampling
            KernelTraceEventParser.Keywords.Memory      // Memory pressure
        );

        // CLR events for GC & exceptions
        session.EnableProvider(
            ClrTraceEventParser.ProviderGuid,
            TraceEventLevel.Informational,
            (ulong)(
                ClrTraceEventParser.Keywords.GC |
                ClrTraceEventParser.Keywords.Exception |
                ClrTraceEventParser.Keywords.Threading
            )
        );

        Console.WriteLine("ETW tracer started");

        var kernel = session.Source.Kernel;

        // --------------------------------------------------
        // PROCESS
        // --------------------------------------------------

        kernel.ProcessStart += evt => Emit(evt, "process_start");
        kernel.ProcessStop += evt => Emit(evt, "process_stop");

        // --------------------------------------------------
        // NETWORK
        // --------------------------------------------------

        kernel.TcpIpSend += evt =>
            Emit(evt, "tcp_send", new { net_bytes = evt.size });

        kernel.TcpIpRecv += evt =>
            Emit(evt, "tcp_recv", new { net_bytes = evt.size });

        // --------------------------------------------------
        // DISK
        // --------------------------------------------------

        kernel.FileIORead += evt =>
            Emit(evt, "file_read", new { disk_bytes = evt.IoSize });

        kernel.FileIOWrite += evt =>
            Emit(evt, "file_write", new { disk_bytes = evt.IoSize });

        // --------------------------------------------------
        // THREAD + CONTEXT SWITCH + OTHER EVENTS
        // --------------------------------------------------

        session.Source.AllEvents += evt =>
        {
            if (evt.ProviderGuid == KernelTraceEventParser.ProviderGuid)
            {
                if (evt.TaskName == "Thread" &&
                    evt.Opcode == (TraceEventOpcode)1)
                {
                    Emit(evt, "thread_start");
                }
                else if (evt.TaskName == "PerfInfo" &&
                         (evt.EventName == "Thread/CSwitch" ||
                          evt.EventName == "PerfInfo/Cswitch"))
                {
                    Emit(evt, "context_switch", new
                    {
                        new_pid = evt.PayloadByName("NewProcessID"),
                        new_tid = evt.PayloadByName("NewThreadID"),
                        reason  = evt.PayloadByName("OldThreadWaitReason")
                    });
                }
                else
                {
                    Emit(evt, evt.EventName);
                }
            }
            else if (evt.ProviderGuid == ClrTraceEventParser.ProviderGuid)
            {
                Emit(evt, evt.EventName);
            }
        };

        session.Source.Process();
    }

    // ===========================================================
    // ✅ SAFE PAYLOAD NORMALIZER (NO JSON CRASH POSSIBLE)
    // ===========================================================

    static object? SafeValue(object? val)
    {
        if (val == null)
            return null;

        // JSON-safe primitives
        if (val is string ||
            val is bool ||
            val is byte || val is short || val is int || val is long ||
            val is float || val is double || val is decimal ||
            val is Guid ||
            val is DateTime ||
            val is DateTimeOffset)
            return val;

        // ✅ IPAddress safely converted
        if (val is IPAddress ip)
            return ip.ToString();

        // ✅ byte[] safety
        if (val is byte[] bytes)
            return Convert.ToBase64String(bytes);

        // ✅ Enum → name
        if (val.GetType().IsEnum)
            return val.ToString();

        // ✅ IEnumerable handling (except strings)
        if (val is IEnumerable enumerable && !(val is string))
        {
            var list = new List<object?>();

            foreach (var item in enumerable)
            {
                list.Add(SafeValue(item));
            }

            return list;
        }

        // ✅ Final safety fallback
        return val.ToString();
    }

    // ===========================================================
    // ✅ SAFE EVENT EMITTER
    // ===========================================================

    static void Emit(TraceEvent evt, string eventType, object? extra = null)
    {
        var payload = new Dictionary<string, object?>();

        foreach (var name in evt.PayloadNames)
        {
            try
            {
                payload[name] = SafeValue(evt.PayloadByName(name));
            }
            catch
            {
                payload[name] = null;
            }
        }

        var obj = new
        {
            //═══════════════════════════════════════
            // ✅ REALTIME UI TIMESTAMP
            //═══════════════════════════════════════
            ts = DateTime.UtcNow.ToString("o"),

            // Kernel precision timeline
            ts_rel_ms = evt.TimeStampRelativeMSec,

            // ---- PROCESS / THREAD ----
            pid = evt.ProcessID,
            tid = evt.ThreadID,

            // ---- CPU ----
            cpu = evt.ProcessorNumber,

            // ---- EVENT ----
            event_type = eventType,

            // ---- PROVIDER ----
            provider = evt.ProviderName,
            provider_guid = evt.ProviderGuid,
            event_name = evt.EventName,
            task = evt.TaskName,
            opcode = evt.OpcodeName,
            opcode_id = (int)evt.Opcode,
            level = evt.Level.ToString(),
            keywords = evt.Keywords,
            version = evt.Version,
            channel = evt.Channel,

            // ---- CORRELATION ----
            activity_id = evt.ActivityID,
            related_activity_id = evt.RelatedActivityID,

            // ---- PAYLOAD ----
            payload_count = evt.PayloadNames.Length,
            payload_size = evt.EventDataLength,
            payload,

            // ---- CUSTOM ----
            net_bytes = extra?.GetType().GetProperty("net_bytes")?.GetValue(extra),
            disk_bytes = extra?.GetType().GetProperty("disk_bytes")?.GetValue(extra),
            new_pid = extra?.GetType().GetProperty("new_pid")?.GetValue(extra),
            new_tid = extra?.GetType().GetProperty("new_tid")?.GetValue(extra),
            reason   = extra?.GetType().GetProperty("reason")?.GetValue(extra)
        };

        Console.WriteLine(JsonSerializer.Serialize(obj));
    }
}
