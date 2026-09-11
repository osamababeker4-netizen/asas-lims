'use strict';
(function () {
  const frame = document.getElementById('branchMapFrame');
  const directions = document.getElementById('branchDirections');
  const cards = Array.from(document.querySelectorAll('.branch-card[data-branch-query]'));
  if (!frame || !directions || !cards.length) return;
  function selectBranch(card) {
    const query = card.dataset.branchQuery;
    const label = card.dataset.branchLabel || card.textContent.trim();
    cards.forEach(function (item) {
      const selected = item === card;
      item.classList.toggle('active', selected);
      item.setAttribute('aria-pressed', String(selected));
    });
    frame.title = label;
    frame.src = 'https://www.google.com/maps?q=' + encodeURIComponent(query) + '&output=embed';
    directions.href = 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(query);
  }
  cards.forEach(function (card) { card.addEventListener('click', function () { selectBranch(card); }); });
  cards.forEach(function (card, index) { card.setAttribute('aria-pressed', String(index === 0)); });
}());
