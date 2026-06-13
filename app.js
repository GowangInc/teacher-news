(function () {
  'use strict';

  const { escapeHtml, formatTime, hostname, hnItemUrl } = window.TN;
  const storiesTable = document.getElementById('stories');

  function getPageFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return parseInt(params.get('p'), 10) || 1;
  }

  function dataUrlForPage(page) {
    return page === 1 ? 'data.json?_=' + Date.now() : 'data-p' + page + '.json?_=' + Date.now();
  }

  function renderStory(story, index) {
    const rank = index + 1;
    const domain = hostname(story.url);
    const domainHtml = domain
      ? ` <span class="sitestr">(${escapeHtml(domain)})</span>`
      : '';
    const commentsCount = story.comment_count || (story.comments || []).length;
    const time = formatTime(story.time);
    const storyUrl = hnItemUrl(story.id);
    const itemPage = `item.html?id=${story.id}`;

    const storyRow = document.createElement('tr');
    storyRow.className = 'story-row';
    storyRow.innerHTML = `
      <td align="right" valign="top" class="rank">${rank}.</td>
      <td valign="top" class="votelinks">
        <div class="votebtn" data-id="${story.id}" title="upvote">▲</div>
      </td>
      <td class="titleline">
        <a href="${storyUrl}">${escapeHtml(story.title)}</a>${domainHtml}
      </td>
    `;

    const voteBtn = storyRow.querySelector('.votebtn');
    voteBtn.addEventListener('click', () => {
      voteBtn.classList.toggle('upvoted');
      const upvoted = voteBtn.classList.contains('upvoted');
      voteBtn.title = upvoted ? 'upvoted' : 'upvote';
      const scoreSpan = document.getElementById(`score-${story.id}`);
      if (scoreSpan) {
        const baseScore = parseInt(scoreSpan.dataset.score, 10);
        scoreSpan.textContent = (baseScore + (upvoted ? 1 : 0)) + ' points';
      }
    });

    const subRow = document.createElement('tr');
    subRow.innerHTML = `
      <td colspan="2"></td>
      <td class="subline">
        <span id="score-${story.id}" data-score="${story.score || 0}">${story.score || 0} points</span>
        by <a href="${storyUrl}">${escapeHtml(story.by || 'teacher')}</a>
        <a href="${storyUrl}">${time}</a>
        | <a href="${itemPage}">${commentsCount} comments</a>
        | <a href="${escapeHtml(story.original_url || story.url || '#')}" title="Original article: ${escapeHtml(story.original_title || story.title)}">source article</a>
      </td>
    `;

    storiesTable.appendChild(storyRow);
    storiesTable.appendChild(subRow);

    const spacer = document.createElement('tr');
    spacer.style.height = '5px';
    storiesTable.appendChild(spacer);
  }

  function addMoreLink(currentPage, totalPages) {
    if (currentPage >= totalPages) return;
    const nextPage = currentPage + 1;
    const spacer = document.createElement('tr');
    spacer.style.height = '10px';
    storiesTable.appendChild(spacer);

    const row = document.createElement('tr');
    row.innerHTML = `
      <td colspan="3" class="more-link">
        <a href="?p=${nextPage}">More</a>
      </td>
    `;
    storiesTable.appendChild(row);
  }

  function addPrevLink(currentPage) {
    if (currentPage <= 1) return;
    const spacer = document.createElement('tr');
    spacer.style.height = '10px';
    storiesTable.appendChild(spacer);

    const row = document.createElement('tr');
    row.innerHTML = `
      <td colspan="3" class="more-link">
        <a href="?p=${currentPage - 1}">&lt; Previous</a>
        &nbsp;|&nbsp;
        <a href="?p=1">Front Page</a>
      </td>
    `;
    storiesTable.appendChild(row);
  }

  function showError(msg) {
    const row = document.createElement('tr');
    row.innerHTML = `<td colspan="3" class="error">${escapeHtml(msg)}</td>`;
    storiesTable.appendChild(row);
  }

  async function init() {
    const page = getPageFromUrl();
    const dataUrl = dataUrlForPage(page);

    // Try pre-rendered content only for page 1
    if (page === 1 && storiesTable.querySelector('.story-row')) {
      // Wire up vote buttons on pre-rendered content
      storiesTable.querySelectorAll('.votebtn').forEach(btn => {
        btn.addEventListener('click', () => {
          btn.classList.toggle('upvoted');
          const upvoted = btn.classList.contains('upvoted');
          btn.title = upvoted ? 'upvoted' : 'upvote';
          const storyId = btn.dataset.id;
          const scoreSpan = document.getElementById(`score-${storyId}`);
          if (scoreSpan) {
            const baseScore = parseInt(scoreSpan.dataset.score, 10);
            scoreSpan.textContent = (baseScore + (upvoted ? 1 : 0)) + ' points';
          }
        });
      });
      // Add navigation for pre-rendered page 1
      try {
        const manifestResp = await fetch('data-manifest.json?_=' + Date.now());
        if (manifestResp.ok) {
          const manifest = await manifestResp.json();
          addMoreLink(1, manifest.total_pages || 999);
        }
      } catch (_) {}
      return;
    }

    try {
      const resp = await fetch(dataUrl);
      if (!resp.ok) {
        if (page > 1) {
          showError('Page ' + page + ' not found. <a href="?p=1">Back to front page</a>');
        } else {
          throw new Error('HTTP ' + resp.status);
        }
        return;
      }
      const data = await resp.json();
      (data.stories || []).forEach(renderStory);

      // Determine total pages from manifest or allow next page attempt
      try {
        const manifestResp = await fetch('data-manifest.json?_=' + Date.now());
        if (manifestResp.ok) {
          const manifest = await manifestResp.json();
          addPrevLink(page);
          addMoreLink(page, manifest.total_pages || (page + 1));
        } else {
          addPrevLink(page);
          addMoreLink(page, page + 1);
        }
      } catch (_) {
        addPrevLink(page);
        addMoreLink(page, page + 1);
      }
    } catch (err) {
      showError('Could not load stories: ' + err.message);
      console.error(err);
    }
  }

  init();
})();
