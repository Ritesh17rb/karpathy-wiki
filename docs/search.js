(function () {
  const dataEl = document.getElementById("searchIndex");
  const input = document.getElementById("searchBox");
  const results = document.getElementById("searchResults");

  if (!dataEl || !input || !results) {
    return;
  }

  const raw = JSON.parse(dataEl.textContent);

  function render(items) {
    results.innerHTML = "";
    if (!items.length) {
      results.innerHTML = "<p>No matches.</p>";
      return;
    }

    items.slice(0, 8).forEach((item) => {
      const wrapper = document.createElement("article");
      wrapper.className = "search-hit";
      wrapper.innerHTML = `
        <a href="${item.url}"><strong>${item.title}</strong></a>
        <span>${item.type}</span>
        <p>${item.summary}</p>
      `;
      results.appendChild(wrapper);
    });
  }

  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    if (!query) {
      results.innerHTML = "";
      return;
    }
    const items = raw.filter((item) => {
      const haystack = [item.title, item.summary, ...(item.keywords || [])].join(" ").toLowerCase();
      return haystack.includes(query);
    });
    render(items);
  });
})();
