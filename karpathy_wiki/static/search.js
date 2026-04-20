(function () {
  const dataEl = document.getElementById("searchIndex");
  const input = document.getElementById("searchBox");
  const results = document.getElementById("searchResults");
  const basePrefix = document.body.dataset.basePrefix || "";

  if (!dataEl || !input || !results) {
    return;
  }

  const raw = JSON.parse(dataEl.textContent);
  const TYPE_PRIORITY = {
    "topic page": 0,
    "source page": 1,
    "wiki page": 2,
  };

  function compareItems(left, right) {
    const leftPriority = TYPE_PRIORITY[left.type] ?? 99;
    const rightPriority = TYPE_PRIORITY[right.type] ?? 99;
    if (leftPriority !== rightPriority) {
      return leftPriority - rightPriority;
    }
    return left.title.localeCompare(right.title);
  }

  function exploreItems() {
    return raw
      .filter((item) => item.type === "topic page" || item.type === "source page")
      .sort(compareItems);
  }

  function render(items) {
    results.innerHTML = "";
    if (!items.length) {
      results.innerHTML = "<p>No matches.</p>";
      return;
    }

    items.slice(0, 8).forEach((item) => {
      const wrapper = document.createElement("article");
      wrapper.className = "search-hit";

      const link = document.createElement("a");
      link.href = `${basePrefix}${item.url}`;
      const strong = document.createElement("strong");
      strong.textContent = item.title;
      link.appendChild(strong);

      const type = document.createElement("span");
      type.textContent = item.type;

      const summary = document.createElement("p");
      summary.textContent = item.summary || "";

      wrapper.appendChild(link);
      wrapper.appendChild(type);
      wrapper.appendChild(summary);
      results.appendChild(wrapper);
    });
  }

  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    if (!query) {
      render(exploreItems());
      return;
    }
    const items = raw.filter((item) => {
      const haystack = [item.title, item.summary, ...(item.keywords || [])].join(" ").toLowerCase();
      return haystack.includes(query);
    });
    render(items.sort(compareItems));
  });

  render(exploreItems());
})();
