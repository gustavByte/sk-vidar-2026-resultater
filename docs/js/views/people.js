import { state } from "../state.js";
import { escapeHtml, formatCount, normalizeSearchText } from "../format.js";
import { hrefPeople, replaceHash } from "../router.js";
import { genderPill, personLink } from "../templates.js";

const current = { search: "", gender: "all", sort: "navn" };

let container = null;
let inputEl = null;
let listEl = null;
let countEl = null;
let sortEl = null;
let genderButtons = null;
let renderFrame = 0;

function genderParamValue() {
  if (current.gender === "women") {
    return "k";
  }
  if (current.gender === "men") {
    return "m";
  }
  return "";
}

function parseGenderParam(value) {
  if (value === "k") {
    return "women";
  }
  if (value === "m") {
    return "men";
  }
  return "all";
}

function syncUrl() {
  replaceHash(
    hrefPeople({
      sok: current.search || "",
      kjonn: genderParamValue(),
      sorter: current.sort !== "navn" ? current.sort : "",
    }),
  );
}

function mount() {
  if (inputEl) {
    return;
  }
  container.innerHTML = `
    <section class="people-shell" aria-label="Personkatalog">
      <div class="section-header">
        <div>
          <p class="section-kicker">Alle løpere</p>
          <h2 class="section-heading">Personer</h2>
        </div>
        <p class="section-copy">Alle med minst ett publisert resultat i 2026. Klikk et navn for full profil.</p>
      </div>
      <div class="people-toolbar">
        <label class="field">
          <span>Søk etter navn</span>
          <input id="people-search" type="search" placeholder="F.eks. Anna" autocomplete="off" />
        </label>
        <div class="segmented" role="group" aria-label="Kjønn">
          <button id="people-gender-all" class="segment is-active" type="button" data-gender="all">Alle</button>
          <button id="people-gender-women" class="segment" type="button" data-gender="women">Kvinner</button>
          <button id="people-gender-men" class="segment" type="button" data-gender="men">Menn</button>
        </div>
        <label class="field">
          <span>Sorter</span>
          <select id="people-sort">
            <option value="navn">Navn (A–Å)</option>
            <option value="resultater">Flest resultater</option>
            <option value="sist">Sist aktiv</option>
          </select>
        </label>
      </div>
      <p id="people-count" class="toolbar-meta"></p>
      <div id="people-list" class="people-list" aria-live="polite"></div>
    </section>
  `;

  inputEl = container.querySelector("#people-search");
  listEl = container.querySelector("#people-list");
  countEl = container.querySelector("#people-count");
  sortEl = container.querySelector("#people-sort");
  genderButtons = Array.from(container.querySelectorAll(".people-toolbar .segment"));

  inputEl.addEventListener("input", (event) => {
    current.search = event.target.value;
    syncUrl();
    cancelAnimationFrame(renderFrame);
    renderFrame = requestAnimationFrame(renderList);
  });

  sortEl.addEventListener("change", (event) => {
    current.sort = event.target.value;
    syncUrl();
    renderList();
  });

  genderButtons.forEach((button) => {
    button.addEventListener("click", () => {
      current.gender = button.dataset.gender;
      syncUrl();
      renderGenderButtons();
      renderList();
    });
  });
}

function renderGenderButtons() {
  genderButtons.forEach((button) => {
    const active = button.dataset.gender === current.gender;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function filteredProfiles() {
  const query = normalizeSearchText(current.search);
  let profiles = state.data.people?.profiles || [];

  if (current.gender === "women") {
    profiles = profiles.filter((profile) => profile.gender === "K");
  } else if (current.gender === "men") {
    profiles = profiles.filter((profile) => profile.gender === "M");
  }
  if (query) {
    profiles = profiles.filter((profile) => normalizeSearchText(profile.display_name).includes(query));
  }

  const sorted = [...profiles];
  if (current.sort === "resultater") {
    sorted.sort((a, b) => Number(b.result_count || 0) - Number(a.result_count || 0) || a.display_name.localeCompare(b.display_name, "nb-NO"));
  } else if (current.sort === "sist") {
    sorted.sort(
      (a, b) =>
        String(b.latest_result_date || "").localeCompare(String(a.latest_result_date || "")) ||
        a.display_name.localeCompare(b.display_name, "nb-NO"),
    );
  } else {
    sorted.sort((a, b) => a.display_name.localeCompare(b.display_name, "nb-NO"));
  }
  return sorted;
}

function personRowHtml(profile) {
  const distances = (profile.distances || []).slice(0, 3);
  const extra = (profile.distances || []).length - distances.length;
  const distancePills = distances.map((distance) => `<span class="result-pill">${escapeHtml(distance)}</span>`).join("");
  return `
    <div class="people-row">
      <span class="people-name">${genderPill(profile.gender)} ${personLink(profile)}</span>
      <span class="people-count-cell">${formatCount(profile.result_count)} resultater</span>
      <span class="people-distances">${distancePills}${extra > 0 ? `<span class="result-pill result-pill--muted">+${extra}</span>` : ""}</span>
      <span class="people-latest muted">${profile.latest_result_date ? `Sist: ${escapeHtml(profile.latest_result_date)}` : ""}</span>
    </div>
  `;
}

function renderList() {
  const profiles = filteredProfiles();
  const total = state.data.people?.profile_count || (state.data.people?.profiles || []).length;
  countEl.textContent = `Viser ${formatCount(profiles.length)} av ${formatCount(total)} personer`;

  if (!profiles.length) {
    listEl.innerHTML = `<p class="empty-state">Ingen personer matcher søket.</p>`;
    return;
  }

  if (current.sort === "navn") {
    const sections = [];
    let currentLetter = "";
    for (const profile of profiles) {
      const letter = (profile.display_name || "?").charAt(0).toLocaleUpperCase("nb-NO");
      if (letter !== currentLetter) {
        currentLetter = letter;
        sections.push(`<h3 class="people-letter" aria-hidden="true">${escapeHtml(letter)}</h3>`);
      }
      sections.push(personRowHtml(profile));
    }
    listEl.innerHTML = sections.join("");
    return;
  }

  listEl.innerHTML = profiles.map(personRowHtml).join("");
}

export function init(viewContainer) {
  container = viewContainer;
}

export function render(params) {
  mount();
  current.search = params.sok || "";
  current.gender = parseGenderParam(params.kjonn || "");
  current.sort = ["navn", "resultater", "sist"].includes(params.sorter) ? params.sorter : "navn";

  if (document.activeElement !== inputEl) {
    inputEl.value = current.search;
  }
  sortEl.value = current.sort;
  renderGenderButtons();
  renderList();
}
