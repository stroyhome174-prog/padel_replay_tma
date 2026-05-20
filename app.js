const tg = window.Telegram?.WebApp;
const API_BASE = "https://dashboard.render.com/project/prj-d86p1vmgvqtc73du7j5g/settings";
let userId = null;
let locationId = null;

function setAuthStatus(text, danger = false) {
const el = document.getElementById("authStatus");
el.textContent = text;
el.style.background = danger ? "#c53030" : "#0f172a";
el.style.color = "#fff";
}

function setFreeRemaining(remaining) {
document.getElementById("btnFree").textContent = `Бесплатно (осталось: ${remaining})`;
}

async function doAuth() {
if (!tg || !tg.initData) {
setAuthStatus("Mini App запущена не в Telegram", true);
return;
}

const res = await fetch(`${API_BASE}/auth`, {
method: "POST",
headers: { "Content-Type": "application/json" },
body: JSON.stringify({ init_ tg.initData })
});

const data = await res.json();

if (data.status !== "ok") {
setAuthStatus(`Ошибка: ${data.detail}`, true);
return;
}

userId = data.user_id;
setAuthStatus(
`ID пользователя: ${userId}
Бесплатно: ${data.free_clips_remaining}
Премиум: ${data.has_premium ? "Да" : "Нет"}`,
false
);

setFreeRemaining(data.free_clips_remaining);
loadLocations();
}

async function loadLocations() {
const locations = [
{ id: 1, name: "Padel Center Chelyabinsk" },
{ id: 2, name: "Padel Club Moscow" }
];

const sel = document.getElementById("locationSelect");
sel.innerHTML = '<option value="">Выберите локацию</option>';
locations.forEach((loc) => {
const opt = document.createElement("option");
opt.value = loc.id;
opt.textContent = loc.name;
sel.appendChild(opt);
});

sel.addEventListener("change", (e) => {
locationId = e.target.value;
localStorage.setItem("locationId", locationId);
localStorage.setItem("timestamp", Date.now());

setTimeout(() => {
const selected = localStorage.getItem("locationId");
if (selected && tg) {
tg.openTelegramLink("https://t.me/your_info_channel");
}
}, 90 * 60 * 1000);
});
}

document.getElementById("btnClip").addEventListener("click", async () => {
if (!userId) {
setAuthStatus("Сначала авторизуйтесь", true);
return;
}
if (!locationId) {
setAuthStatus("Выберите локацию", true);
return;
}

document.getElementById("status").textContent = "Отправляем запрос на сервер...";

const res = await fetch(`${API_BASE}/trigger_clip`, {
method: "POST",
headers: { "Content-Type": "application/json" },
body: JSON.stringify({ user_id: userId, location_id: locationId, pay: false })
});

const data = await res.json();

if (data.status !== "ok") {
setAuthStatus(`Ошибка: ${data.detail || "unknown"}`, true);
return;
}

setFreeRemaining(data.free_clips_remaining);
document.getElementById("status").textContent = `Видео готово: ${data.video_url}`;
tg?.showAlert(`Видео готово!\n${data.video_url}`);
});

async function handlePayment(type, amount) {
if (!userId) {
setAuthStatus("Сначала авторизуйтесь", true);
return;
}

setAuthStatus("Открываем платёжную форму...");

const res = await fetch(`${API_BASE}/payment/${type}`, {
method: "POST",
headers: { "Content-Type": "application/json" },
body: JSON.stringify({ user_id: userId, amount })
});

const data = await res.json();

if (data.status !== "ok") {
setAuthStatus(`Ошибка: ${data.detail || "payment error"}`, true);
return;
}

if (tg) tg.openLink(data.payment_url);
}

document.getElementById("btnSingle").addEventListener("click", () => handlePayment("single", 50));
document.getElementById("btnUnlimited").addEventListener("click", () => handlePayment("unlimited", 400));
document.getElementById("btnVip").addEventListener("click", () => handlePayment("vip", 650));

document.getElementById("btnStorage").addEventListener("click", async () => {
if (!userId) {
tg?.showAlert("Авторизуйтесь сначала!");
return;
}

const res = await fetch(`${API_BASE}/feed`);
const data = await res.json();

const links = (data.clips || []).map((c) => c.video_url).join("\n");
tg?.showAlert(links ? `Ваши видео:\n${links}` : "Видео пока нет");
});

doAuth();
