import { state, loadData } from "./js/state.js";
import { hrefSearch, parseHash, replaceHash } from "./js/router.js";
import * as dashboardView from "./js/views/dashboard.js";
import * as weekView from "./js/views/week.js";
import * as peopleView from "./js/views/people.js";
import * as profileView from "./js/views/profile.js";
import * as statsView from "./js/views/stats.js?v=20260708-highlights1";
import * as searchView from "./js/views/search.js";

const views = {
  dashboard: dashboardView,
  week: weekView,
  people: peopleView,
  person: profileView,
  stats: statsView,
  search: searchView,
};

// Which nav tab is highlighted for each view.
const tabForView = {
  dashboard: "dashboard",
  week: "week",
  people: "people",
  person: "people",
  stats: "stats",
  search: "",
};

const containers = {};

function grabContainers() {
  containers.dashboard = document.getElementById("view-dashboard");
  containers.week = document.getElementById("view-week");
  containers.people = document.getElementById("view-people");
  containers.person = document.getElementById("view-profile");
  containers.stats = document.getElementById("view-stats");
  containers.search = document.getElementById("view-search");
}

function setActiveTab(view) {
  const tab = tabForView[view] ?? "";
  document.querySelectorAll(".nav-tab").forEach((link) => {
    const active = link.dataset.tab === tab;
    link.classList.toggle("is-active", active);
    if (active) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
}

function showView(view) {
  Object.entries(containers).forEach(([key, element]) => {
    element.hidden = key !== view;
  });
}

function renderRoute() {
  const route = parseHash(window.location.hash);
  if (route.replace) {
    window.location.replace(route.replace);
    return;
  }
  showView(route.view);
  setActiveTab(route.view);
  views[route.view].render(route.params);
}

function bindNavSearch() {
  const form = document.getElementById("nav-search-form");
  const input = document.getElementById("nav-search-input");
  if (!form || !input) {
    return;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    window.location.hash = hrefSearch(input.value);
  });

  input.addEventListener("input", () => {
    // Live-update only when the search view is already open.
    if (parseHash(window.location.hash).view === "search") {
      replaceHash(hrefSearch(input.value));
      searchView.render({ q: input.value });
    }
  });
}

function renderLastUpdated() {
  const element = document.getElementById("last-updated");
  if (!element) {
    return;
  }
  element.textContent = `Oppdatert ${new Date(state.data.generated_at).toLocaleString("nb-NO", {
    dateStyle: "long",
    timeStyle: "short",
  })}`;
}

function showLoadError(error) {
  console.error(error);
  const element = document.getElementById("load-error");
  if (element) {
    element.hidden = false;
    element.textContent = "Data kunne ikke lastes. Kjør bygge-skriptet på nytt for å lage JSON-filen.";
  }
}

async function main() {
  grabContainers();
  bindNavSearch();

  try {
    await loadData();
  } catch (error) {
    showLoadError(error);
    return;
  }

  Object.entries(views).forEach(([key, view]) => {
    if (typeof view.init === "function") {
      view.init(containers[key]);
    }
  });

  renderLastUpdated();
  renderRoute();
  window.addEventListener("hashchange", renderRoute);
}

main();
