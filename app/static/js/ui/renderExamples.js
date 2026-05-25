import { buildDisplayPath } from "../core/request.js";

const LABELS = {
  linha: "Linha",
  codigo_paragem: "Código paragem",
  codigo: "Código paragem",
  sentido: "Sentido (ida/volta)",
  nome: "Nome da paragem",
  lat: "Latitude",
  lon: "Longitude",
  raio: "Raio (metros)",
};

export function renderTabs(container, tabs, activeTab, onSelect) {
  container.innerHTML = "";
  tabs.forEach((tab) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `tab ${tab.id === activeTab ? "active" : ""}`;
    btn.dataset.tab = tab.id;
    btn.textContent = tab.label;
    btn.onclick = () => onSelect(tab.id);
    container.appendChild(btn);
  });
}

export function renderExampleCards(container, exemplos, endpointsById, onTest) {
  container.innerHTML = "";

  if (!exemplos.length) {
    container.innerHTML = '<p class="empty-msg">Nenhum exemplo nesta secção.</p>';
    return;
  }

  exemplos.forEach((exemplo) => {
    const endpoint = endpointsById[exemplo.endpointId];
    if (!endpoint) return;

    const card = document.createElement("article");
    card.className = `example-card accent-${exemplo.accent}`;
    card.dataset.exampleId = exemplo.id;

    const question = document.createElement("p");
    question.className = "example-question";
    question.textContent = exemplo.pergunta;

    const endpointLine = document.createElement("code");
    endpointLine.className = "example-endpoint";
    endpointLine.dataset.role = "path-preview";

    const paramsWrap = document.createElement("div");
    paramsWrap.className = "example-params";

    const paramsState = { ...exemplo.params };

    function refreshPath() {
      endpointLine.textContent = buildDisplayPath(endpoint, paramsState);
    }

    (exemplo.editaveis || []).forEach((key) => {
      const mini = document.createElement("div");
      mini.className = "mini-field";
      const label = document.createElement("label");
      label.textContent = LABELS[key] || key;
      const input = document.createElement("input");
      input.value = paramsState[key] ?? "";
      input.dataset.param = key;
      input.addEventListener("input", () => {
        paramsState[key] = input.value;
        refreshPath();
      });
      mini.appendChild(label);
      mini.appendChild(input);
      paramsWrap.appendChild(mini);
    });

    refreshPath();

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-test";
    btn.textContent = "Testar";
    btn.onclick = () => onTest(exemplo, endpoint, { ...paramsState }, card);

    card.appendChild(question);
    card.appendChild(endpointLine);
    if (exemplo.editaveis?.length) card.appendChild(paramsWrap);
    card.appendChild(btn);
    container.appendChild(card);
  });
}
