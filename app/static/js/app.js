import { ENDPOINTS } from "./data/endpoints.js";
import { EXEMPLOS, TABS } from "./data/examples.js";
import { dom } from "./core/dom.js";
import { loadConnect, saveConnect } from "./core/storage.js";
import { buildRequest, runHttpRequest } from "./core/request.js";
import { renderTabs, renderExampleCards } from "./ui/renderExamples.js";

const endpointsById = Object.fromEntries(ENDPOINTS.map((item) => [item.id, item]));
let tabAtiva = "todos";

function exemplosFiltrados() {
  if (tabAtiva === "todos") return EXEMPLOS;
  return EXEMPLOS.filter((item) => item.tab === tabAtiva);
}

function persistConnect() {
  saveConnect(dom.baseUrl.value.trim(), dom.apiKey.value.trim());
}

function showResult({ pergunta, displayPath, full, ok, statusText, body, elapsedMs }) {
  dom.resultPanel.classList.remove("hidden");
  dom.resultTitle.textContent = pergunta;
  dom.resultUrl.textContent = full;
  dom.resultBadge.textContent = ok ? `${statusText} · ${elapsedMs}ms` : statusText;
  dom.resultBadge.className = `badge ${ok ? "ok" : "err"}`;
  dom.resultBody.textContent = body;
  dom.resultPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function formatBody(rawText) {
  try {
    return JSON.stringify(JSON.parse(rawText), null, 2);
  } catch {
    return rawText;
  }
}

async function testarExemplo(exemplo, endpoint, params, card) {
  const baseUrl = dom.baseUrl.value.trim();
  if (!baseUrl) {
    showResult({
      pergunta: exemplo.pergunta,
      displayPath: "",
      full: "",
      ok: false,
      statusText: "Falta URL",
      body: "Preenche a URL da API em Ligação.",
      elapsedMs: 0,
    });
    return;
  }

  persistConnect();
  card.classList.add("is-loading");
  dom.resultPanel.classList.remove("hidden");
  dom.resultBadge.className = "badge wait";
  dom.resultBadge.textContent = "A pedir…";
  dom.resultTitle.textContent = exemplo.pergunta;

  const { full, displayPath } = buildRequest(endpoint, params, baseUrl);
  dom.resultUrl.textContent = full;

  try {
    const { response, text, elapsedMs } = await runHttpRequest(endpoint.metodo, full, dom.apiKey.value);
    showResult({
      pergunta: exemplo.pergunta,
      displayPath,
      full,
      ok: response.ok,
      statusText: `${response.status} ${response.statusText}`,
      body: formatBody(text),
      elapsedMs,
    });
  } catch (error) {
    showResult({
      pergunta: exemplo.pergunta,
      displayPath,
      full,
      ok: false,
      statusText: "Erro de rede",
      body: String(error),
      elapsedMs: 0,
    });
  } finally {
    card.classList.remove("is-loading");
  }
}

function render() {
  renderTabs(dom.tabs, TABS, tabAtiva, (tabId) => {
    tabAtiva = tabId;
    render();
  });
  renderExampleCards(dom.examples, exemplosFiltrados(), endpointsById, testarExemplo);
}

function showBootError(msg) {
  const el = document.getElementById("bootError");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("hidden");
}

function init() {
  try {
    const saved = loadConnect();
    dom.baseUrl.value = saved?.baseUrl || `${window.location.protocol}//${window.location.host}`;
    dom.apiKey.value = saved?.apiKey || "";

    dom.baseUrl.addEventListener("input", persistConnect);
    dom.apiKey.addEventListener("input", persistConnect);

    render();
  } catch (error) {
    showBootError(`Erro ao iniciar o frontend: ${error.message}`);
    console.error(error);
  }
}

init();
