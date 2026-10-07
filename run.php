<?php
// ==========================================
// কনফিগারেশন সেটিংস
// ==========================================
$cpanel_username = "chepbota"; 
$app_folder      = "myotpbot"; 
$python_version  = "3.11"; 

// পাথ কনফিগারেশন
$base_dir     = "/home/{$cpanel_username}/{$app_folder}";
$python_path  = "/home/{$cpanel_username}/virtualenv/{$app_folder}/{$python_version}/bin/python";
$script_path  = "{$base_dir}/main.py";
$log_path     = "{$base_dir}/bot_output.log";

// ফাইল সমূহ
$control_file = "{$base_dir}/bot_control.txt";
$status_file  = "{$base_dir}/bot_status.json";
$worker_file  = "{$base_dir}/cron_worker.sh";
$pid_file     = "{$base_dir}/daemon.pid";

// ডিরেক্টরি নিশ্চিত করা
if (!is_dir($base_dir)) {
    @mkdir($base_dir, 0755, true);
}

// ইনস্ট্যান্ট ব্যাকগ্রাউন্ড স্ক্রিপ্ট (Daemon Loop) তৈরি করা
$worker_script_content = <<<BASH
#!/bin/bash
APP_DIR="{$base_dir}"
PYTHON_BIN="{$python_path}"
SCRIPT="{$script_path}"
CONTROL_FILE="{$control_file}"
STATUS_FILE="{$status_file}"
LOG_FILE="{$log_path}"
PID_FILE="{$pid_file}"

# একাধিক ডেমন চালু হওয়া রোধ করা
if [ -f "\$PID_FILE" ]; then
    OLD_PID=\$(cat "\$PID_FILE" 2>/dev/null)
    if [ -n "\$OLD_PID" ] && kill -0 "\$OLD_PID" 2>/dev/null; then
        exit 0
    fi
fi

echo \$\$ > "\$PID_FILE"

# রিয়েল-টাইম লিসেনার লুপ (সর্বদা সচল থাকে)
while true; do
    NOW=\$(date +%s)
    ACTION=\$(cat "\$CONTROL_FILE" 2>/dev/null || echo "")
    BOT_PID=\$(pgrep -f "\$SCRIPT" | head -n 1)

    if [ "\$ACTION" = "START" ]; then
        if [ -z "\$BOT_PID" ]; then
            export HOME="/home/{$cpanel_username}"
            cd "\$APP_DIR"
            nohup "\$PYTHON_BIN" "\$SCRIPT" >> "\$LOG_FILE" 2>&1 </dev/null &
            sleep 0.8
            BOT_PID=\$(pgrep -f "\$SCRIPT" | head -n 1)
        fi
        STATUS="RUNNING"
    elif [ "\$ACTION" = "STOP" ]; then
        if [ -n "\$BOT_PID" ]; then
            pkill -f "\$SCRIPT"
            BOT_PID=""
        fi
        STATUS="STOPPED"
    else
        if [ -n "\$BOT_PID" ]; then
            STATUS="RUNNING"
        else
            STATUS="STOPPED"
        fi
    fi

    # সেফ এবং অ্যাটমিক স্ট্যাটাস রাইটিং
    echo "{\"cron_last_run\": \$NOW, \"status\": \"\$STATUS\", \"pid\": \"\$BOT_PID\"}" > "\$STATUS_FILE.tmp"
    mv -f "\$STATUS_FILE.tmp" "\$STATUS_FILE"

    sleep 1
done
BASH;

if (!file_exists($worker_file) || file_get_contents($worker_file) !== $worker_script_content) {
    file_put_contents($worker_file, $worker_script_content);
    chmod($worker_file, 0755);
}

// ফাংশন: বর্তমান স্ট্যাটাস রিড করা
function get_current_bot_status($file) {
    if (file_exists($file)) {
        clearstatcache(true, $file);
        $data = json_decode(file_get_contents($file), true);
        if ($data) return $data;
    }
    return ['cron_last_run' => 0, 'status' => 'STOPPED', 'pid' => ''];
}

$action = isset($_GET['action']) ? $_GET['action'] : '';
$message = '';
$status_class = '';

// ক্রন জব সচল কি না যাচাই (সর্বোচ্চ ১৫ সেকেন্ডের মধ্যে হার্টবিট থাকতে হবে)
$init_status = get_current_bot_status($status_file);
$cron_active = ((time() - $init_status['cron_last_run']) <= 15);

// ইনস্ট্যান্ট অ্যাকশন প্রসেসিং
if ($action == 'start') {
    file_put_contents($control_file, "START");
    
    if ($cron_active) {
        // ক্রন জব ১ সেকেন্ডে ক্যাচ করার জন্য ১.৫ সেকেন্ড অপেক্ষা করা
        for ($i = 0; $i < 6; $i++) {
            usleep(300000); // ০.৩ সেকেন্ড বিরতি
            $chk = get_current_bot_status($status_file);
            if ($chk['status'] === 'RUNNING' && !empty($chk['pid'])) {
                $message = "বটটি সফলভাবে তাৎক্ষণিক চালু করা হয়েছে! (PID: " . $chk['pid'] . ")";
                $status_class = 'success';
                break;
            }
        }
        if (empty($message)) {
            $message = "চালু করার নির্দেশ দেওয়া হয়েছে! কয়েক মুহূর্তের মধ্যে চালু হয়ে যাবে।";
            $status_class = 'warning';
        }
    } else {
        $message = "অন করার কমান্ড দেওয়া হয়েছে, তবে ক্রন জব সক্রিয় নেই! দয়া করে cPanel-এ ক্রন জব যোগ করুন।";
        $status_class = 'warning';
    }
} elseif ($action == 'stop') {
    file_put_contents($control_file, "STOP");
    
    if ($cron_active) {
        for ($i = 0; $i < 6; $i++) {
            usleep(300000);
            $chk = get_current_bot_status($status_file);
            if ($chk['status'] === 'STOPPED') {
                $message = "বটটি তাৎক্ষণিকভাবে বন্ধ করা হয়েছে!";
                $status_class = 'error';
                break;
            }
        }
        if (empty($message)) {
            $message = "বন্ধ করার নির্দেশ পাঠানো হয়েছে!";
            $status_class = 'warning';
        }
    } else {
        $message = "অফ করার কমান্ড সেট হয়েছে, ক্রন জব চালু হলে এটি বন্ধ হবে।";
        $status_class = 'warning';
    }
}

// ফাইনাল স্ট্যাটাস আপডেট
$final_data = get_current_bot_status($status_file);
$bot_status = $final_data['status'];
$bot_pid    = $final_data['pid'];
$cron_active = ((time() - $final_data['cron_last_run']) <= 15);

$cron_command = "bash {$worker_file} >/dev/null 2>&1";
?>
<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instant Bot & Cron Manager</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px 0;
        }
        .container {
            background-color: var(--card-bg);
            padding: 2.2rem;
            border-radius: 16px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
            width: 90%;
            max-width: 480px;
            text-align: center;
            border: 1px solid #334155;
            position: relative;
        }
        h1 { font-size: 1.6rem; margin: 0 0 0.4rem 0; font-weight: 600; }
        .subtitle { color: var(--text-muted); font-size: 0.85rem; margin-bottom: 1.5rem; }

        .status-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 1.5rem;
        }
        .status-box {
            background-color: #0f172a;
            border-radius: 10px;
            padding: 1rem;
            border: 1px solid #334155;
            display: flex;
            flex-direction: column;
            gap: 6px;
            align-items: center;
        }
        .status-title { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
        .status-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 600;
            font-size: 1rem;
        }
        .status-dot { width: 10px; height: 10px; border-radius: 50%; }
        .dot-green { background-color: var(--success); box-shadow: 0 0 8px var(--success); }
        .dot-red { background-color: var(--danger); box-shadow: 0 0 8px var(--danger); }
        .dot-yellow { background-color: var(--warning); box-shadow: 0 0 8px var(--warning); }

        .pulse { animation: pulseAnim 1.6s infinite; }
        @keyframes pulseAnim {
            0% { transform: scale(0.95); opacity: 0.8; }
            70% { transform: scale(1.2); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.8; }
        }

        .cron-box {
            background-color: #0b1120;
            border: 1px dashed #475569;
            border-radius: 10px;
            padding: 1rem;
            margin-bottom: 1.5rem;
            text-align: left;
        }
        .cron-box-title {
            font-size: 0.8rem;
            color: #38bdf8;
            font-weight: 600;
            margin-bottom: 6px;
        }
        .cron-code {
            background: #1e293b;
            padding: 10px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 0.82rem;
            color: #f1f5f9;
            word-break: break-all;
            user-select: all;
            margin-bottom: 10px;
            border: 1px solid #334155;
        }
        .btn-copy {
            background: #0284c7;
            color: #fff;
            border: none;
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.8rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 6px;
            width: fit-content;
        }
        .btn-copy:hover { background: #0369a1; }

        .alert {
            padding: 0.85rem 1rem;
            border-radius: 8px;
            margin-bottom: 1.5rem;
            font-size: 0.9rem;
            text-align: center;
        }
        .alert-success { background-color: rgba(16, 185, 129, 0.15); border: 1px solid var(--success); color: #34d399; }
        .alert-error { background-color: rgba(239, 68, 68, 0.15); border: 1px solid var(--danger); color: #f87171; }
        .alert-warning { background-color: rgba(245, 158, 11, 0.15); border: 1px solid var(--warning); color: #fbbf24; }

        .btn-group {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
            margin-bottom: 1rem;
        }
        .btn {
            padding: 0.9rem 1rem;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 1rem;
            cursor: pointer;
            transition: all 0.2s ease;
            text-decoration: none;
            color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        .btn-start { background-color: var(--success); }
        .btn-start:hover { background-color: #059669; }
        .btn-stop { background-color: var(--danger); }
        .btn-stop:hover { background-color: #dc2626; }
        .btn-status { grid-column: span 2; background-color: var(--primary); }
        .btn-status:hover { background-color: #2563eb; }

        .footer {
            margin-top: 1.5rem;
            font-size: 0.75rem;
            color: var(--text-muted);
            border-top: 1px solid #334155;
            padding-top: 0.8rem;
        }

        .loading-overlay {
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(15, 23, 42, 0.85);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            z-index: 999;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s ease;
        }
        .loading-overlay.show { opacity: 1; pointer-events: auto; }
        .spinner {
            width: 45px; height: 45px;
            border: 4px solid rgba(255, 255, 255, 0.1);
            border-top: 4px solid var(--primary);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>

    <div id="loadingOverlay" class="loading-overlay">
        <div class="spinner"></div>
        <div style="margin-top: 15px; font-weight: 600; color: #fff;">প্রসেস করা হচ্ছে, অপেক্ষা করুন...</div>
    </div>

    <div class="container">
        <h1>Bot Manager</h1>
        <div class="subtitle">Instant Execution Control Panel</div>

        <div class="status-grid">
            <!-- বট স্ট্যাটাস -->
            <div class="status-box">
                <span class="status-title">Bot Status</span>
                <span class="status-badge" style="color: <?php echo ($bot_status === 'RUNNING') ? 'var(--success)' : 'var(--danger)'; ?>;">
                    <span class="status-dot <?php echo ($bot_status === 'RUNNING') ? 'dot-green pulse' : 'dot-red'; ?>"></span>
                    <?php echo $bot_status; ?>
                </span>
                <?php if (!empty($bot_pid)): ?>
                    <span style="font-size: 0.7rem; color: var(--text-muted);">PID: <?php echo htmlspecialchars($bot_pid); ?></span>
                <?php endif; ?>
            </div>

            <!-- ক্রন জব স্ট্যাটাস -->
            <div class="status-box">
                <span class="status-title">Cronjob Status</span>
                <span class="status-badge" style="color: <?php echo $cron_active ? 'var(--success)' : 'var(--warning)'; ?>;">
                    <span class="status-dot <?php echo $cron_active ? 'dot-green' : 'dot-yellow'; ?>"></span>
                    <?php echo $cron_active ? 'ACTIVE' : 'INACTIVE'; ?>
                </span>
                <span style="font-size: 0.7rem; color: var(--text-muted);">
                    <?php echo $cron_active ? 'লাইভ সচল আছে' : 'ক্রন চালু করা হয়নি'; ?>
                </span>
            </div>
        </div>

        <?php if (!empty($message)): ?>
            <div class="alert alert-<?php echo $status_class; ?>">
                <?php echo htmlspecialchars($message); ?>
            </div>
        <?php endif; ?>

        <!-- ক্রন কমান্ড এবং কপি সেকশন -->
        <div class="cron-box">
            <div class="cron-box-title">cPanel Cron Job Command (Once Per Minute):</div>
            <div class="cron-code" id="cronCommandText"><?php echo htmlspecialchars($cron_command); ?></div>
            <button class="btn-copy" onclick="copyCronCommand()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                <span id="copyBtnText">Copy Command</span>
            </button>
        </div>

        <!-- কন্ট্রোল বাটন -->
        <div class="btn-group">
            <a href="?action=start" class="btn btn-start" onclick="showLoader()">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                Start Bot
            </a>
            <a href="?action=stop" class="btn btn-stop" onclick="showLoader()">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect></svg>
                Off Bot
            </a>
            <a href="?action=status" class="btn btn-status" onclick="showLoader()">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path></svg>
                Refresh Status
            </a>
        </div>

        <div class="footer">
            Schedule: <code>* * * * *</code> | Instant Daemon Monitoring
        </div>
    </div>

    <script>
        function showLoader() {
            document.getElementById('loadingOverlay').classList.add('show');
        }

        function copyCronCommand() {
            var text = document.getElementById("cronCommandText").innerText;
            navigator.clipboard.writeText(text).then(function() {
                var btnText = document.getElementById("copyBtnText");
                btnText.innerText = "Copied!";
                setTimeout(function() { btnText.innerText = "Copy Command"; }, 2000);
            }).catch(function(err) {
                alert("কপি করা যায়নি, অনুগ্রহ করে নিজে সিলেক্ট করে কপি করুন।");
            });
        }
    </script>
</body>
</html>