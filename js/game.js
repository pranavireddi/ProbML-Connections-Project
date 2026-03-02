document.addEventListener("DOMContentLoaded", () => {
  const gridEl = document.getElementById("grid");
  const statusEl = document.getElementById("status-message");
  const mistakesEl = document.getElementById("mistakes");
  const submitBtn = document.getElementById("submit-btn");
  const deselectBtn = document.getElementById("deselect-btn");
  const shuffleBtn = document.getElementById("shuffle-btn");
  const resetBtn = document.getElementById("reset-btn");

  // Simple placeholder puzzle: numbers instead of real words.
  // Tiles 1-4, 5-8, 9-12, 13-16 form the four hidden groups.
  let tiles = Array.from({ length: 16 }, (_, i) => ({
    id: i,
    label: String(i + 1),
    group: Math.floor(i / 4) + 1,
  }));

  let selectedIds = new Set();
  let solvedGroups = new Set();
   // Track the order in which groups are solved so rows appear like NYT.
  let solvedOrder = [];
  let mistakesRemaining = 4;

  function shuffleTiles() {
    const solvedTiles = tiles.filter((t) => solvedGroups.has(t.group));
    let unsolvedTiles = tiles.filter((t) => !solvedGroups.has(t.group));

    unsolvedTiles = unsolvedTiles
      .map((t) => ({ ...t, sort: Math.random() }))
      .sort((a, b) => a.sort - b.sort)
      .map(({ sort, ...rest }) => rest);

    const orderedSolved = [];
    solvedOrder.forEach((groupId) => {
      const groupTiles = solvedTiles
        .filter((t) => t.group === groupId)
        .sort((a, b) => a.id - b.id);
      orderedSolved.push(...groupTiles);
    });

    tiles = [...orderedSolved, ...unsolvedTiles];
    renderGrid();
  }

  function renderGrid() {
    gridEl.innerHTML = "";
    const solvedTiles = [];
    const unsolvedTiles = [];

    tiles.forEach((tile) => {
      if (solvedGroups.has(tile.group)) {
        solvedTiles.push(tile);
      } else {
        unsolvedTiles.push(tile);
      }
    });

    const orderedSolved = [];
    solvedOrder.forEach((groupId) => {
      const groupTiles = solvedTiles
        .filter((t) => t.group === groupId)
        .sort((a, b) => a.id - b.id);
      orderedSolved.push(...groupTiles);
    });

    const renderTiles = [...orderedSolved, ...unsolvedTiles];

    renderTiles.forEach((tile) => {
      const tileEl = document.createElement("button");
      tileEl.className = "tile";
      tileEl.textContent = tile.label;
      tileEl.dataset.id = tile.id;

      const isSelected = selectedIds.has(tile.id);
      const isSolved = solvedGroups.has(tile.group);

      if (isSolved) {
        tileEl.classList.add("tile-solved", `tile-group-${tile.group}`);
        tileEl.disabled = true;
      } else if (isSelected) {
        tileEl.classList.add("tile-selected");
      }

      tileEl.addEventListener("click", () => onTileClick(tile));
      gridEl.appendChild(tileEl);
    });
  }

  function onTileClick(tile) {
    if (solvedGroups.has(tile.group)) return;

    if (selectedIds.has(tile.id)) {
      selectedIds.delete(tile.id);
    } else {
      if (selectedIds.size >= 4) {
        flashStatus("You can only select four tiles.", true);
        return;
      }
      selectedIds.add(tile.id);
    }

    renderGrid();
    clearStatus();
  }

  function handleSubmit() {
    if (selectedIds.size !== 4) {
      flashStatus("Select exactly four tiles.", true);
      return;
    }

    const selectedTiles = tiles.filter((t) => selectedIds.has(t.id));
    const groupId = selectedTiles[0].group;
    const allSameGroup = selectedTiles.every((t) => t.group === groupId);

    if (allSameGroup && !solvedGroups.has(groupId)) {
      solvedGroups.add(groupId);
      solvedOrder.push(groupId);
      selectedIds.clear();
      renderGrid();
      flashStatus("Nice! You found a group.", false);

      if (solvedGroups.size === 4) {
        flashStatus("Puzzle complete!", false);
        submitBtn.disabled = true;
        deselectBtn.disabled = true;
        shuffleBtn.disabled = true;
      }
    } else {
      mistakesRemaining = Math.max(0, mistakesRemaining - 1);
      mistakesEl.textContent = `Mistakes remaining: ${mistakesRemaining}`;
      flashStatus("Not quite. Try a different set.", true);

      if (mistakesRemaining === 0) {
        submitBtn.disabled = true;
      }
    }
  }

  function handleDeselect() {
    selectedIds.clear();
    renderGrid();
    clearStatus();
  }

  function handleReset() {
    selectedIds.clear();
    solvedGroups.clear();
    solvedOrder = [];
    mistakesRemaining = 4;

    submitBtn.disabled = false;
    deselectBtn.disabled = false;
    shuffleBtn.disabled = false;

    shuffleTiles();
    clearStatus();
    mistakesEl.textContent = `Mistakes remaining: ${mistakesRemaining}`;
  }

  function flashStatus(message, isError) {
    statusEl.textContent = message;
    statusEl.classList.toggle("status-error", Boolean(isError));
  }

  function clearStatus() {
    statusEl.textContent = "Select four tiles.";
    statusEl.classList.remove("status-error");
  }

  submitBtn.addEventListener("click", handleSubmit);
  deselectBtn.addEventListener("click", handleDeselect);
  shuffleBtn.addEventListener("click", () => {
    handleDeselect();
    shuffleTiles();
  });
  resetBtn.addEventListener("click", handleReset);

  // Initial render
  shuffleTiles();
  clearStatus();
  mistakesEl.textContent = `Mistakes remaining: ${mistakesRemaining}`;
});
