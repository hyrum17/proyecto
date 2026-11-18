const form = document.getElementById("search-form");
const locationInput = document.getElementById("location");
const categoryInput = document.getElementById("category");
const radiusInput = document.getElementById("radius");
const button = document.getElementById("search-button");
const resultsEl = document.getElementById("results");
const statusEl = document.getElementById("status");
const countEl = document.getElementById("result-count");
const noticeEl = document.getElementById("notice");

const map = L.map("map").setView([39.5, -111.5], 6);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);

let markers = L.layerGroup().addTo(map);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;"
  }[char]));
}

function resourceCard(item) {
  const website = item.website && /^https?:\/\//i.test(item.website)
    ? `<a href="${escapeHtml(item.website)}" target="_blank" rel="noopener">Sitio web</a>` : "";
  const phone = item.phone
    ? `<a href="tel:${escapeHtml(item.phone.replace(/[^\d+]/g, ""))}">Llamar</a>` : "";
  const directions = `https://www.google.com/maps/dir/?api=1&destination=${item.lat},${item.lon}`;
  return `<article class="resource-card">
    <span class="distance">${item.distance_km.toFixed(2)} km de distancia</span>
    <h3>${escapeHtml(item.name)}</h3>
    <p>${escapeHtml(item.address)}</p>
    ${item.phone ? `<p>Teléfono: ${escapeHtml(item.phone)}</p>` : ""}
    <div class="resource-links">
      ${website}${phone}
      <a href="${directions}" target="_blank" rel="noopener">Cómo llegar</a>
      <a href="${escapeHtml(item.osm_url)}" target="_blank" rel="noopener">Ver fuente</a>
    </div>
  </article>`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const location = locationInput.value.trim();
  if (!location) return;

  button.disabled = true;
  button.textContent = "Buscando...";
  statusEl.textContent = "Localizando la ciudad y consultando recursos cercanos...";
  countEl.textContent = "";
  noticeEl.classList.add("hidden");
  resultsEl.innerHTML = "";
  markers.clearLayers();

  const params = new URLSearchParams({
    location,
    category: categoryInput.value,
    radius_km: radiusInput.value
  });

  try {
    const response = await fetch(`/api/search?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "No se pudo completar la búsqueda.");

    statusEl.textContent = data.location;
    countEl.textContent = `${data.count} resultado(s)`;
    noticeEl.textContent = data.notice;
    noticeEl.classList.remove("hidden");

    if (!data.results.length) {
      resultsEl.innerHTML = `<div class="empty-state"><div class="empty-icon">⌖</div><h3>No encontramos resultados registrados</h3><p>Prueba aumentando la distancia o seleccionando otra categoría. También puedes llamar al 211 en Estados Unidos.</p></div>`;
    } else {
      resultsEl.innerHTML = data.results.map(resourceCard).join("");
    }

    const center = [data.coordinates.lat, data.coordinates.lon];
    L.circle(center, {radius: Number(radiusInput.value) * 1000, color: "#2764d8", fillOpacity: 0.04}).addTo(markers);
    L.marker(center).bindPopup(`<strong>${escapeHtml(location)}</strong><br>Ubicación buscada`).addTo(markers);
    data.results.forEach(item => {
      L.marker([item.lat, item.lon])
        .bindPopup(`<strong>${escapeHtml(item.name)}</strong><br>${item.distance_km} km`)
        .addTo(markers);
    });
    const points = [center, ...data.results.map(item => [item.lat, item.lon])];
    map.fitBounds(L.latLngBounds(points).pad(0.15), {maxZoom: 13});
  } catch (error) {
    statusEl.textContent = "No se pudo completar la búsqueda.";
    resultsEl.innerHTML = `<div class="empty-state"><h3>Ocurrió un problema</h3><p>${escapeHtml(error.message)}</p><p>Comprueba tu conexión e inténtalo otra vez.</p></div>`;
  } finally {
    button.disabled = false;
    button.innerHTML = 'Buscar recursos <span aria-hidden="true">→</span>';
  }
});
