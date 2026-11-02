/**
 * Raindrop UI — çoklu oturum + pywebview köprüsü.
 * API hataları exception yerine {ok:false} — Gönder kilidi olmaz.
 */

/** @type {string[]} */
let attachmentPaths = [];
/** @type {string|null} */
let activeSessionId = null;
/** @type {Array<Record<string, unknown>>} */
let sessionsCache = [];

function $(id) {
  return document.getElementById(id);
}

function setStatus(text, tone) {
  const pill = $("statusPill");
  const label = $("statusText");
  if (!pill || !label) return;
  label.textContent = text;
  pill.dataset.tone = tone || "idle";
}

function clearFieldErrors() {
  document.querySelectorAll(".field.is-invalid").forEach((el) => {
    el.classList.remove("is-invalid");
  });
}

function markFieldError(fieldId) {
  if (!fieldId) return;
  const el = $(fieldId);
  if (!el) return;
  const field = el.closest(".field");
  if (field) field.classList.add("is-invalid");
  try {
    el.focus();
  } catch (_) {
    /* ignore */
  }
}

function renderAttachments() {
  const list = $("attachmentList");
  if (!list) return;
  list.innerHTML = "";
  if (!attachmentPaths.length) {
    const empty = document.createElement("span");
    empty.className = "compose-hint";
    empty.textContent = "Ek yok";
    list.appendChild(empty);
    return;
  }
  attachmentPaths.forEach((path, index) => {
    const chip = document.createElement("div");
    chip.className = "chip";
    const name = path.split(/[/\\]/).pop() || path;
    const span = document.createElement("span");
    span.textContent = name;
    span.title = path;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", `${name} kaldır`);
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      attachmentPaths.splice(index, 1);
      renderAttachments();
    });
    chip.appendChild(span);
    chip.appendChild(remove);
    list.appendChild(chip);
  });
}

function todayIso() {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function nowHm() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** @returns {string|null} normalize HH:MM or null */
function normalizeHm(raw) {
  const v = String(raw || "").trim();
  const m = v.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h > 23 || min > 59) return null;
  return `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
}

function wireTimeInput(id) {
  const el = $(id);
  if (!el || el.dataset.timeWired) return;
  el.dataset.timeWired = "1";
  el.addEventListener("blur", () => {
    const n = normalizeHm(el.value);
    if (n) el.value = n;
  });
  el.addEventListener("input", () => {
    let t = el.value.replace(/[^\d:]/g, "");
    if (t.length === 2 && !t.includes(":")) t = `${t}:`;
    if (t.length > 5) t = t.slice(0, 5);
    el.value = t;
  });
}

function setSendBusy(busy, label) {
  const btn = $("btnSend");
  if (!btn) return;
  btn.disabled = !!busy;
  if (busy) btn.setAttribute("aria-busy", "true");
  else btn.removeAttribute("aria-busy");
  if (label) btn.textContent = label;
  else btn.textContent = "Gönder";
}

/**
 * Arka plan gönderimini yoklar; UI'yi kilitlemez.
 * @returns {Promise<Record<string, unknown>>}
 */
function pollSendJob(timeoutMs) {
  const started = Date.now();
  return new Promise((resolve) => {
    const tick = async () => {
      try {
        const job = await api("get_send_job");
        if (job && job.message) setStatus(job.message, job.busy ? "busy" : "idle");
        if (!job || !job.busy) {
          resolve(job || { busy: false, result: null, message: "Bitti" });
          return;
        }
        if (Date.now() - started > timeoutMs) {
          resolve({
            busy: false,
            timedOut: true,
            message: "Zaman aşımı — gönderim arka planda sürebilir; logu kontrol et.",
            result: {
              ok: false,
              message: "Gönderim zaman aşımına uğradı (UI açıldı).",
            },
          });
          return;
        }
      } catch (err) {
        resolve({
          busy: false,
          message: String(err),
          result: { ok: false, message: String(err) },
        });
        return;
      }
      setTimeout(tick, 400);
    };
    tick();
  });
}

function selectedWeekdays() {
  return Array.from(
    document.querySelectorAll("#weekdayGrid input[type='checkbox']:checked")
  ).map((el) => el.value);
}

function setWeekdays(days) {
  const set = new Set(days || []);
  document.querySelectorAll("#weekdayGrid input[type='checkbox']").forEach((el) => {
    el.checked = set.has(el.value);
  });
}

function getFrequency() {
  const el = document.querySelector('input[name="scheduleFrequency"]:checked');
  return el ? el.value : "weekly";
}

function setFrequency(freq) {
  const target = document.querySelector(
    `input[name="scheduleFrequency"][value="${freq}"]`
  );
  if (target) target.checked = true;
}

function setSelectValue(id, value, fallback) {
  const el = $(id);
  if (!el) return;
  const v = value || fallback;
  const has = Array.from(el.options).some((o) => o.value === v || o.text === v);
  if (has) {
    el.value = v;
  } else if (fallback) {
    el.value = fallback;
  }
}

function syncAdvancedDisabled() {
  $("delayFor").disabled = !$("delayEnabled").checked;
  const rep = $("repeatEnabled").checked;
  $("repeatEvery").disabled = !rep;
  $("repeatFor").disabled = !rep;
  $("repeatStopAtEnd").disabled = !rep;
  $("stopLongerFor").disabled = !$("stopLongerEnabled").checked;
  const exp = $("expireEnabled").checked;
  $("expireDate").disabled = !exp;
  $("expireTime").disabled = !exp;
}

function updateScheduleVisibility() {
  const freq = getFrequency();
  const showInterval = freq === "daily" || freq === "weekly";
  const showWeekdays = freq === "weekly";
  const showMonthDay = freq === "monthly";

  $("wrapInterval").hidden = !showInterval;
  $("wrapWeekdays").hidden = !showWeekdays;
  $("wrapMonthDay").hidden = !showMonthDay;
  $("wrapInterval").style.display = showInterval ? "" : "none";
  $("wrapWeekdays").style.display = showWeekdays ? "" : "none";
  $("wrapMonthDay").style.display = showMonthDay ? "" : "none";
  $("intervalUnit").textContent =
    freq === "daily" ? "günde bir" : "haftada bir";
  syncAdvancedDisabled();
}

function applySchedule(sched) {
  if (!sched) return;
  $("scheduleEnabled").checked = !!sched.enabled;
  setFrequency(sched.frequency || "weekly");
  $("scheduleTime").value = sched.time || "09:00";
  $("scheduleStartDate").value = sched.start_date || todayIso();
  $("scheduleSyncTz").checked = !!sched.sync_timezones;
  $("scheduleInterval").value = String(sched.interval || 1);
  $("scheduleMonthDay").value = String(sched.month_day || 1);
  setWeekdays(sched.weekdays || ["mon", "tue", "wed", "thu", "fri"]);

  $("delayEnabled").checked = !!sched.delay_enabled;
  setSelectValue("delayFor", sched.delay_for, "1 hour");
  $("repeatEnabled").checked = !!sched.repeat_enabled;
  setSelectValue("repeatEvery", sched.repeat_every, "20 minutes");
  setSelectValue("repeatFor", sched.repeat_for, "8 hours");
  $("repeatStopAtEnd").checked = !!sched.repeat_stop_at_end;
  $("stopLongerEnabled").checked = !!sched.stop_if_runs_longer_enabled;
  setSelectValue("stopLongerFor", sched.stop_if_runs_longer, "3 days");
  $("expireEnabled").checked = !!sched.expire_enabled;
  $("expireDate").value = sched.expire_date || todayIso();
  $("expireTime").value = sched.expire_time || "21:00";

  $("scheduleStatus").textContent = sched.message || "";
  updateScheduleVisibility();
}

function collectSchedulePayload() {
  return {
    enabled: $("scheduleEnabled").checked,
    frequency: getFrequency(),
    time: $("scheduleTime").value || "09:00",
    start_date: $("scheduleStartDate").value || todayIso(),
    sync_timezones: $("scheduleSyncTz").checked,
    interval: Number($("scheduleInterval").value || 1),
    weekdays: selectedWeekdays(),
    month_day: Number($("scheduleMonthDay").value || 1),
    delay_enabled: $("delayEnabled").checked,
    delay_for: $("delayFor").value,
    repeat_enabled: $("repeatEnabled").checked,
    repeat_every: $("repeatEvery").value,
    repeat_for: $("repeatFor").value,
    repeat_stop_at_end: $("repeatStopAtEnd").checked,
    stop_if_runs_longer_enabled: $("stopLongerEnabled").checked,
    stop_if_runs_longer: $("stopLongerFor").value,
    expire_enabled: $("expireEnabled").checked,
    expire_date: $("expireDate").value || todayIso(),
    expire_time: $("expireTime").value || "21:00",
  };
}

function applyAccount(account) {
  if (!account) return;
  $("gmailAddress").value = account.gmail_address || "";
  $("reportEmail").value = account.report_email || "";
  $("smtpPort").value = account.smtp_port || "587";
  $("appPassword").value = "";
  $("appPassword").placeholder = account.app_password_set
    ? "Kayıtlı · değiştirmek için yeni şifre yaz"
    : "16 haneli Uygulama Şifresi";
}

function applySession(session, schedule, summary) {
  if (!session) return;
  activeSessionId = session.id;
  $("sessionName").value = session.name || "Oturum";
  $("recipients").value = session.recipients || "";
  $("subject").value = session.subject || "";
  $("body").value = session.body || "";
  $("sessionReportEmail").value = session.report_email || "";

  const raw = session.attachment_path || "";
  attachmentPaths = raw
    ? raw.split(";").map((p) => p.trim()).filter(Boolean)
    : [];
  renderAttachments();

  if (schedule) applySchedule(schedule);
  else if (session.schedule) applySchedule(session.schedule);

  const meta = summary || {};
  const bits = [];
  if (meta.schedule_active) bits.push("Otomasyon aktif");
  else if (meta.schedule_enabled) bits.push("Otomasyon kayıt bekliyor");
  else bits.push("Elle gönderim");
  if (meta.schedule_summary) bits.push(meta.schedule_summary);
  $("sessionMeta").textContent = bits.join(" · ");
}

function renderSessionsList() {
  const root = $("sessionsList");
  if (!root) return;
  root.innerHTML = "";

  if (!sessionsCache.length) {
    const empty = document.createElement("p");
    empty.className = "compose-hint";
    empty.textContent = "Oturum yok — + ile ekle";
    root.appendChild(empty);
    return;
  }

  sessionsCache.forEach((item) => {
    const card = document.createElement("div");
    card.className =
      "session-card" + (item.id === activeSessionId ? " is-active" : "");
    card.setAttribute("role", "listitem");
    card.dataset.id = item.id;

    const top = document.createElement("div");
    top.className = "session-card-top";
    const name = document.createElement("div");
    name.className = "session-card-name";
    name.textContent = item.name || "Oturum";
    const badge = document.createElement("span");
    const pending =
      !item.schedule_active && !!item.schedule_enabled;
    badge.className =
      "session-badge" +
      (item.schedule_active ? " is-on" : pending ? " is-warn" : "");
    badge.textContent = item.schedule_active
      ? "Aktif"
      : pending
        ? "Kayıt eksik"
        : "Kapalı";
    top.appendChild(name);
    top.appendChild(badge);

    const meta = document.createElement("p");
    meta.className = "session-card-meta";
    const rc = item.recipient_count || 0;
    meta.textContent = `${rc} alıcı · ${item.schedule_summary || "zamanlama yok"}`;

    const actions = document.createElement("div");
    actions.className = "session-card-actions";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.textContent = item.schedule_active || item.schedule_enabled ? "Durdur" : "Başlat";
    toggle.addEventListener("click", (ev) => {
      ev.stopPropagation();
      onToggleAutomation(item.id, !(item.schedule_active || item.schedule_enabled));
    });

    const del = document.createElement("button");
    del.type = "button";
    del.className = "danger";
    del.textContent = "Sil";
    del.addEventListener("click", (ev) => {
      ev.stopPropagation();
      onDeleteSession(item.id);
    });

    actions.appendChild(toggle);
    actions.appendChild(del);

    card.appendChild(top);
    card.appendChild(meta);
    card.appendChild(actions);
    card.addEventListener("click", () => onSelectSession(item.id));
    root.appendChild(card);
  });
}

/**
 * @param {{ applySchedule?: boolean }} [opts]
 */
function collectSessionPayload(opts) {
  const applySchedule = !opts || opts.applySchedule !== false;
  const time = normalizeHm($("scheduleTime").value) || "09:00";
  const expireTime = normalizeHm($("expireTime").value) || "21:00";
  $("scheduleTime").value = time;
  $("expireTime").value = expireTime;
  const schedule = collectSchedulePayload();
  schedule.time = time;
  schedule.expire_time = expireTime;
  return {
    id: activeSessionId,
    name: $("sessionName").value.trim() || "Oturum",
    recipients: $("recipients").value.trim(),
    subject: $("subject").value.trim(),
    body: $("body").value,
    attachment_path: attachmentPaths.join(";"),
    report_email: $("sessionReportEmail").value.trim(),
    gmail_address: $("gmailAddress").value.trim(),
    app_password: $("appPassword").value,
    account_report_email: $("reportEmail").value.trim(),
    smtp_host: "smtp.gmail.com",
    smtp_port: $("smtpPort").value.trim() || "587",
    schedule,
    apply_schedule: applySchedule,
  };
}

function validateBeforeSend() {
  clearFieldErrors();
  const recipients = $("recipients").value.trim();
  const gmail = $("gmailAddress").value.trim();
  const report =
    $("sessionReportEmail").value.trim() || $("reportEmail").value.trim();

  if (!gmail) {
    markFieldError("gmailAddress");
    return "Gmail adresi gerekli.";
  }
  if (!report) {
    markFieldError("reportEmail");
    switchTab("account");
    return "Hata raporu adresi gerekli.";
  }
  if (!recipients) {
    markFieldError("recipients");
    return "En az bir alıcı gerekli.";
  }
  return null;
}

async function api(method, ...args) {
  if (!window.pywebview || !window.pywebview.api) {
    throw new Error("pywebview API henüz hazır değil.");
  }
  const fn = window.pywebview.api[method];
  if (typeof fn !== "function") {
    throw new Error(`API metodu yok: ${method}`);
  }
  return fn(...args);
}

async function refreshLog() {
  try {
    const text = await api("get_log_tail");
    $("logView").textContent = text || "Log boş.";
  } catch (err) {
    $("logView").textContent = String(err);
  }
}

function switchTab(tabName) {
  document.querySelectorAll(".tab").forEach((btn) => {
    const active = btn.dataset.tab === tabName;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    const active = panel.id === `panel-${tabName}`;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
  if (tabName === "activity") refreshLog();
}

function ingestListPayload(data) {
  if (!data) return;
  sessionsCache = Array.isArray(data.sessions) ? data.sessions : sessionsCache;
  if (data.active_id) activeSessionId = data.active_id;
  if (data.account) applyAccount(data.account);
  renderSessionsList();
}

async function loadSessionDetail(sessionId) {
  const data = await api("get_session", sessionId);
  if (!data || data.ok === false) {
    setStatus((data && data.message) || "Oturum yüklenemedi", "err");
    return;
  }
  applySession(data.session, data.schedule, data.summary);
  if (data.account) applyAccount(data.account);
  if (Array.isArray(data.sessions)) {
    sessionsCache = data.sessions;
  }
  renderSessionsList();
}

async function loadInitial() {
  setStatus("Yükleniyor…", "busy");
  clearFieldErrors();
  try {
    if (!$("scheduleStartDate").value) $("scheduleStartDate").value = todayIso();
    if (!$("expireDate").value) $("expireDate").value = todayIso();

    const listed = await api("list_sessions");
    ingestListPayload(listed);
    const sid = (listed && listed.active_id) || (sessionsCache[0] && sessionsCache[0].id);
    if (sid) {
      await loadSessionDetail(sid);
    }
    await refreshLog();
    setStatus("Hazır", "idle");
  } catch (err) {
    setStatus(String(err), "err");
  }
}

async function onSelectSession(sessionId) {
  if (!sessionId || sessionId === activeSessionId) return;
  setStatus("Oturum açılıyor…", "busy");
  try {
    const data = await api("select_session", sessionId);
    if (!data || data.ok === false) {
      setStatus((data && data.message) || "Seçilemedi", "err");
      return;
    }
    ingestListPayload(data);
    applySession(data.session, data.schedule, data.summary);
    setStatus(`Oturum: ${data.session.name}`, "ok");
  } catch (err) {
    setStatus(err.message || String(err), "err");
  }
}

async function onNewSession() {
  setStatus("Yeni oturum…", "busy");
  try {
    const data = await api("create_session", "");
    if (!data || data.ok === false) {
      setStatus((data && data.message) || "Oluşturulamadı", "err");
      return;
    }
    ingestListPayload(data);
    applySession(data.session, data.schedule, data.summary);
    setStatus("Yeni oturum oluşturuldu", "ok");
  } catch (err) {
    setStatus(err.message || String(err), "err");
  }
}

async function onDeleteSession(sessionId) {
  if (!sessionId) return;
  const ok = window.confirm("Bu oturum ve zamanlaması silinsin mi?");
  if (!ok) return;
  setStatus("Siliniyor…", "busy");
  try {
    const data = await api("delete_session", sessionId);
    if (!data || data.ok === false) {
      setStatus((data && data.message) || "Silinemedi", "err");
      return;
    }
    ingestListPayload(data);
    if (data.session) {
      applySession(data.session, data.schedule, data.summary);
    }
    setStatus(data.message || "Silindi", "ok");
  } catch (err) {
    setStatus(err.message || String(err), "err");
  }
}

async function onToggleAutomation(sessionId, enabled) {
  setStatus(enabled ? "Otomasyon başlatılıyor…" : "Durduruluyor…", "busy");
  try {
    // Aktif oturumdaysa formu da kaydetmeden sadece bayrak
    if (sessionId === activeSessionId) {
      $("scheduleEnabled").checked = !!enabled;
      const saved = await api("save_session", collectSessionPayload());
      if (!saved || saved.ok === false) {
        markFieldError(saved && saved.field);
        setStatus((saved && saved.message) || "Kaydedilemedi", "err");
        return;
      }
      ingestListPayload(saved);
      applySession(saved.session, saved.schedule, saved.summary);
      setStatus(saved.message || "Güncellendi", saved.ok === false ? "err" : "ok");
      return;
    }

    const data = await api("set_session_automation", sessionId, !!enabled);
    if (!data || data.ok === false) {
      setStatus((data && data.message) || "Güncellenemedi", "err");
      return;
    }
    ingestListPayload(data);
    setStatus(data.message || "Güncellendi", "ok");
  } catch (err) {
    setStatus(err.message || String(err), "err");
  }
}

async function onSave() {
  clearFieldErrors();
  setStatus("Kaydediliyor…", "busy");
  $("btnSave").disabled = true;
  try {
    const clientErr = validateBeforeSend();
    // Kaydette alıcı boş olabilir (taslak) — sadece rapor/hesap
    if (!($("reportEmail").value.trim() || $("sessionReportEmail").value.trim())) {
      markFieldError("reportEmail");
      switchTab("account");
      setStatus("Hata raporu adresi gerekli.", "err");
      return;
    }
    if (!$("gmailAddress").value.trim()) {
      markFieldError("gmailAddress");
      switchTab("account");
      setStatus("Gmail adresi gerekli.", "err");
      return;
    }
    void clientErr;

    const data = await api("save_session", collectSessionPayload());
    if (!data || data.ok === false) {
      markFieldError(data && data.field);
      setStatus((data && data.message) || "Kayıt başarısız", "err");
      await refreshLog();
      return;
    }
    ingestListPayload(data);
    applySession(data.session, data.schedule, data.summary);
    if (data.account) applyAccount(data.account);
    setStatus(data.message || "Kaydedildi", "ok");
    await refreshLog();
  } catch (err) {
    setStatus(err.message || String(err), "err");
    await refreshLog();
  } finally {
    $("btnSave").disabled = false;
  }
}

async function runBackgroundSend(sessionId) {
  setSendBusy(true, "Gönderiliyor…");
  setStatus("Gönderim başlatılıyor…", "busy");
  try {
    const started = await api("start_send", sessionId || "");
    if (!started || started.ok === false || !started.started) {
      setStatus((started && started.message) || "Gönderim başlatılamadı", "err");
      return null;
    }
    setStatus(started.message || "SMTP bağlanıyor…", "busy");
    const job = await pollSendJob(90000);
    const result = (job && job.result) || null;
    if (job && job.timedOut) {
      setStatus(job.message, "err");
      switchTab("activity");
      await refreshLog();
      return result;
    }
    if (result && result.ok) {
      setStatus(result.message || "Gönderildi", "ok");
    } else {
      setStatus(
        (result && result.message) || (job && job.message) || "Gönderim başarısız",
        "err"
      );
    }
    await refreshLog();
    return result;
  } catch (err) {
    setStatus(err.message || String(err), "err");
    await refreshLog();
    return null;
  } finally {
    setSendBusy(false);
  }
}

async function onSend() {
  clearFieldErrors();
  const err = validateBeforeSend();
  if (err) {
    setStatus(err, "err");
    return;
  }

  setSendBusy(true, "Kaydediliyor…");
  setStatus("Kaydediliyor…", "busy");
  try {
    const saved = await api(
      "save_session",
      collectSessionPayload({ applySchedule: false })
    );
    if (!saved || saved.ok === false) {
      markFieldError(saved && saved.field);
      setStatus((saved && saved.message) || "Kayıt başarısız — gönderilmedi", "err");
      await refreshLog();
      setSendBusy(false);
      return;
    }
    ingestListPayload(saved);
    applySession(saved.session, saved.schedule, saved.summary);
  } catch (e) {
    setStatus(e.message || String(e), "err");
    setSendBusy(false);
    return;
  }

  await runBackgroundSend(activeSessionId || "");
}

/** Tarih/saati şimdiye alır, otomasyonu kaydeder ve bir kez gönderir. */
async function onStartNow() {
  clearFieldErrors();
  const err = validateBeforeSend();
  if (err) {
    setStatus(err, "err");
    if (err.includes("rapor") || err.includes("Gmail")) switchTab("account");
    else switchTab("schedule");
    return;
  }

  $("scheduleStartDate").value = todayIso();
  $("scheduleTime").value = nowHm();
  $("scheduleEnabled").checked = true;
  switchTab("schedule");

  setSendBusy(true, "Başlatılıyor…");
  setStatus("Şimdi başlatılıyor — kaydediliyor…", "busy");
  try {
    const saved = await api(
      "save_session",
      collectSessionPayload({ applySchedule: true })
    );
    if (!saved || saved.ok === false) {
      markFieldError(saved && saved.field);
      setStatus((saved && saved.message) || "Kayıt başarısız", "err");
      setSendBusy(false);
      await refreshLog();
      return;
    }
    ingestListPayload(saved);
    applySession(saved.session, saved.schedule, saved.summary);
    setStatus("Otomasyon kaydedildi — şimdi bir kez gönderiliyor…", "busy");
  } catch (e) {
    setStatus(e.message || String(e), "err");
    setSendBusy(false);
    return;
  }

  await runBackgroundSend(activeSessionId || "");
}

async function onAttach() {
  try {
    const picked = await api("pick_attachments");
    if (!Array.isArray(picked) || !picked.length) return;
    const set = new Set(attachmentPaths);
    picked.forEach((p) => set.add(p));
    attachmentPaths = Array.from(set);
    renderAttachments();
    setStatus(`${picked.length} dosya eklendi`, "ok");
  } catch (err) {
    setStatus(err.message || String(err), "err");
  }
}

function onClearAttach() {
  attachmentPaths = [];
  renderAttachments();
  setStatus("Ekler temizlendi", "idle");
}

function wireWindowControls() {
  const minBtn = $("btnMin");
  const closeBtn = $("btnClose");
  if (minBtn) {
    minBtn.addEventListener("click", async () => {
      try {
        await api("minimize");
      } catch (_) {
        /* önizleme */
      }
    });
  }
  if (closeBtn) {
    closeBtn.addEventListener("click", async () => {
      try {
        await api("close_window");
      } catch (_) {
        window.close();
      }
    });
  }
}

function wire() {
  $("btnSave").addEventListener("click", onSave);
  $("btnSend").addEventListener("click", onSend);
  $("btnAttach").addEventListener("click", onAttach);
  $("btnClearAttach").addEventListener("click", onClearAttach);
  $("btnRefreshLog").addEventListener("click", () => {
    switchTab("activity");
    refreshLog();
  });
  $("btnNewSession").addEventListener("click", onNewSession);
  if ($("btnStartNow")) {
    $("btnStartNow").addEventListener("click", onStartNow);
  }
  wireTimeInput("scheduleTime");
  wireTimeInput("expireTime");
  wireWindowControls();

  document.querySelectorAll('input[name="scheduleFrequency"]').forEach((el) => {
    el.addEventListener("change", updateScheduleVisibility);
  });
  ["delayEnabled", "repeatEnabled", "stopLongerEnabled", "expireEnabled"].forEach(
    (id) => {
      $(id).addEventListener("change", syncAdvancedDisabled);
    }
  );

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  renderAttachments();
  updateScheduleVisibility();
}

window.addEventListener("pywebviewready", () => {
  wire();
  loadInitial();
});

document.addEventListener("DOMContentLoaded", () => {
  if (!window.pywebview) {
    wire();
    $("scheduleStartDate").value = todayIso();
    $("expireDate").value = todayIso();
    setStatus("Önizleme (köprü yok)", "idle");
    $("logView").textContent = "pywebview içinde çalıştırıldığında log görünür.";
  }
});
