document.addEventListener("DOMContentLoaded", () => {
  const gridEl = document.getElementById("grid");
  const statusEl = document.getElementById("status-message");
  const mistakesEl = document.getElementById("mistakes");
  const submitBtn = document.getElementById("submit-btn");
  const deselectBtn = document.getElementById("deselect-btn");
  const shuffleBtn = document.getElementById("shuffle-btn");
  const resetBtn = document.getElementById("reset-btn");

  let tiles = [];
  let currentPuzzle = null;

  let selectedIds = new Set();
  let solvedGroups = new Set();
  let solvedOrder = [];
  let mistakesRemaining = 4;

  let revealAnswersMode = false;

  function buildTilesFromPuzzle(puzzle) {
    const memberToGroup = new Map();

    puzzle.groups.forEach((groupObj, index) => {
      const groupId = index + 1;
      groupObj.members.forEach((word) => {
        memberToGroup.set(String(word).trim().toUpperCase(), {
          id: groupId,
          color: groupObj.color,
          title: groupObj.group,
          explanation: groupObj.explanation || ""
        });
      });
    });

    return puzzle.board.map((word, index) => {
      const normalized = String(word).trim().toUpperCase();
      const groupInfo = memberToGroup.get(normalized);

      if (!groupInfo) {
        throw new Error(`Word "${word}" was in board but not found in any group.`);
      }

      return {
        id: index,
        label: normalized,
        group: groupInfo.id,
        color: groupInfo.color,
        title: groupInfo.title,
        explanation: groupInfo.explanation
      };
    });
  }

  async function loadPuzzle() {
    flashStatus("Loading puzzle...", false);

    const response = await fetch("/api/puzzle");
    if (!response.ok) {
      throw new Error("Failed to load puzzle");
    }

    currentPuzzle = await response.json();
    tiles = buildTilesFromPuzzle(currentPuzzle);

    selectedIds.clear();
    solvedGroups.clear();
    solvedOrder = [];
    mistakesRemaining = 4;
    revealAnswersMode = false;

    submitBtn.disabled = false;
    deselectBtn.disabled = false;
    shuffleBtn.disabled = false;

    renderGrid();
    clearStatus();
    mistakesEl.textContent = `Mistakes remaining: ${mistakesRemaining}`;
  }

  function shuffleTiles() {
    const solvedTiles = tiles.filter((t) => solvedGroups.has(t.group));
    let unsolvedTiles = tiles.filter((t) => !solvedGroups.has(t.group));

    unsolvedTiles = unsolvedTiles
      .map((t) => ({ ...t, sort: Math.random() }))
      .sort((a, b) => a.sort - b.sort)
      .map(({ sort, ...rest }) => rest);

    const orderedSolved = [];
    solvedOrder.forEach((groupId) => {
      const groupTiles = solvedTiles.filter((t) => t.group === groupId);
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

    // Render solved/revealed groups in solvedOrder
    solvedOrder.forEach((groupId) => {
      const groupTiles = solvedTiles.filter((t) => t.group === groupId);

      if (groupTiles.length === 0) return;

      // Show category bar only when answers are being revealed
      if (revealAnswersMode) {
        const bannerEl = document.createElement("div");
        bannerEl.className = "group-banner";

        const titleEl = document.createElement("div");
        titleEl.className = "group-banner-title";
        titleEl.textContent = groupTiles[0].title;

        const wordsEl = document.createElement("div");
        wordsEl.className = "group-banner-words";
        wordsEl.textContent = groupTiles.map((t) => t.label).join(", ");

        bannerEl.appendChild(titleEl);
        bannerEl.appendChild(wordsEl);
        gridEl.appendChild(bannerEl);
      }

      groupTiles.forEach((tile) => {
        const tileEl = document.createElement("button");
        tileEl.className = "tile";
        tileEl.textContent = tile.label;
        tileEl.dataset.id = tile.id;

        tileEl.classList.add("tile-solved", `tile-group-${tile.group}`);
        tileEl.disabled = true;

        gridEl.appendChild(tileEl);
      });
    });

    // Then render remaining unsolved tiles normally
    unsolvedTiles.forEach((tile) => {
      const tileEl = document.createElement("button");
      tileEl.className = "tile";
      tileEl.textContent = tile.label;
      tileEl.dataset.id = tile.id;

      const isSelected = selectedIds.has(tile.id);

      if (isSelected) {
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

  function revealAllAnswers() {
    const allGroupIds = [...new Set(tiles.map((t) => t.group))];

    allGroupIds.forEach((groupId) => {
      if (!solvedGroups.has(groupId)) {
        solvedGroups.add(groupId);
        solvedOrder.push(groupId);
      }
    });

    revealAnswersMode = true;
    selectedIds.clear();
    renderGrid();
    flashStatus("Out of tries. The correct groups are shown below.", true);
  }

  function showAnswerSummary() {
    const groups = solvedOrder.map((groupId) => {
      const groupTiles = tiles
        .filter((t) => t.group === groupId)
        .sort((a, b) => a.label.localeCompare(b.label));

      if (groupTiles.length === 0) return null;

      return `${groupTiles[0].title}: ${groupTiles.map((t) => t.label).join(", ")}`;
    }).filter(Boolean);

    flashStatus(`Out of tries. Answers: ${groups.join(" | ")}`, true);
  }

  function handleSubmit() {
    if (selectedIds.size !== 4) {
      flashStatus("Select exactly four tiles.", true);
      return;
    }

    if (mistakesRemaining === 0) {
      submitBtn.disabled = true;
      deselectBtn.disabled = true;
      shuffleBtn.disabled = true;
      revealAllAnswers();
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

      const solvedTile = selectedTiles[0];
      flashStatus(`Nice! ${solvedTile.title}`, false);

      if (solvedGroups.size === 4) {
        flashStatus("Puzzle complete!", false);
        submitBtn.disabled = true;
        deselectBtn.disabled = true;
        shuffleBtn.disabled = true;
      }
    } else {
      mistakesRemaining = Math.max(0, mistakesRemaining - 1);
      mistakesEl.textContent = `Mistakes remaining: ${mistakesRemaining}`;

      if (mistakesRemaining === 0) {
        submitBtn.disabled = true;
        deselectBtn.disabled = true;
        shuffleBtn.disabled = true;
        revealAllAnswers();
        return;
      }

      flashStatus("Not quite. Try a different set.", true);
    }
  }

  function handleDeselect() {
    selectedIds.clear();
    renderGrid();
    clearStatus();
  }

  async function handleReset() {
    try {
      await loadPuzzle();
    } catch (error) {
      flashStatus("Could not load a new puzzle.", true);
      console.error(error);
    }
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

  loadPuzzle().catch((error) => {
    flashStatus("Failed to load puzzle.", true);
    console.error(error);
  });
});