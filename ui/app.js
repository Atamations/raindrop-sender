/**
 * Raindrop UI — pywebview bridge istemcisi.
 */

/** @type {string[]} */
let attachmentPaths = [];

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

function collectPayload(includePassword) {
  const payload = {
    gmail_address: $("gmailAddress").value.trim(),
    recipients: $("recipients").value.trim(),
    report_email: $("reportEmail").value.trim(),
    smtp_host: "smtp.gmail.com",
    smtp_port: $("smtpPort").value.trim() || "587",
    subject: $("subject").value.trim(),
    body: $("body").value,
    attachment_path: attachmentPaths.join(";"),
  };
  if (includePassword) {
    payload.app_password = $("appPassword").value;
  }
  return payload;
}

function applyConfig(cfg) {
  if (!cfg) return;
  $("gmailAddress").value = cfg.gmail_address || "";
  $("recipients").value = cfg.recipients || "";
  $("reportEmail").value = cfg.report_email || "";
  $("smtpPort").value = cfg.smtp_port || "587";
  $("subject").value = cfg.subject || "";
  $("body").value = cfg.body || "";
  $("appPassword").value = "";
  $("appPassword").placeholder = cfg.app_password_set
    ? "Kayıtlı · değiştirmek için yeni şifre yaz"
    : "16 haneli Uygulama Şifresi";

  const raw = cfg.attachment_path || "";
  attachmentPaths = raw
    ? raw.split(";").map((p) => p.trim()).filter(Boolean)
    : [];
  renderAttachments();
}

function todayIso() {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
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

  // display yedek — bazı WebView sürümlerinde [hidden] yetmez
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

async function loadSchedule() {
  const sched = await api("get_schedule");
  applySchedule(sched);
}

async function saveScheduleFromUi() {
  return api("save_schedule", collectSchedulePayload());
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

async function loadInitial() {
  setStatus("Yükleniyor…", "busy");
  try {
    if (!$("scheduleStartDate").value) $("scheduleStartDate").value = todayIso();
    if (!$("expireDate").value) $("expireDate").value = todayIso();
    const cfg = await api("get_config");
    applyConfig(cfg);
    await loadSchedule();
    await refreshLog();
    setStatus(cfg.env_exists ? "Hazır" : ".env yok — ayarları kaydet", "idle");
  } catch (err) {
    setStatus(String(err), "err");
  }
}

async function onSave() {
  setStatus("Kaydediliyor…", "busy");
  $("btnSave").disabled = true;
  try {
    const cfg = await api("save_config", collectPayload(true));
    applyConfig(cfg);
    const sched = await saveScheduleFromUi();
    applySchedule(sched);
    setStatus("Ayarlar ve zamanlama kaydedildi", "ok");
    await refreshLog();
  } catch (err) {
    setStatus(err.message || String(err), "err");
  } finally {
    $("btnSave").disabled = false;
  }
}

async function onSend() {
  const btn = $("btnSend");
  btn.disabled = true;
  btn.setAttribute("aria-busy", "true");
  setStatus("Gönderiliyor…", "busy");
  try {
    await api("save_config", collectPayload(true));
    const result = await api("send_mail");
    if (result && result.ok) {
      setStatus(result.message || "Gönderildi", "ok");
    } else {
      setStatus((result && result.message) || "Gönderim başarısız", "err");
    }
    await refreshLog();
  } catch (err) {
    setStatus(err.message || String(err), "err");
    await refreshLog();
  } finally {
    btn.disabled = false;
    btn.removeAttribute("aria-busy");
  }
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
