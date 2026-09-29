/* CodeMemory - app.js
   Static demo frontend. Reads data/results.json only.
   No network calls to backend LLM APIs. */

(function () {
  'use strict';

  let DATA = null;
  let currentPRIndex = 0;
  let mergedPRs = new Set();
  let currentView = 'pr';
  let guidedRunning = false;
  let guidedPaused = false;
  let guidedTimer = null;

  function renderImpactPanel() {
    const p = document.getElementById('impact-panel');
    const s = document.getElementById('impact-stats');
    if (!DATA || !DATA.impact || !p || !s) return;
    if (Object.keys(DATA.impact).length > 0 || (DATA.meta && DATA.meta.source !== "synthetic-fixture")) {
        p.style.display = 'block';
        let src = DATA.meta && DATA.meta.source ? DATA.meta.source : 'Unknown';
        let toks = DATA.meta && DATA.meta.usage ? DATA.meta.usage.llm_tokens : 0;
        let c = DATA.meta && DATA.meta.usage ? DATA.meta.usage.llm_calls : 0;
        let rs = DATA.meta && DATA.meta.privacy_summary && DATA.meta.privacy_summary.counts ? Object.keys(DATA.meta.privacy_summary.counts).length : 0;
        s.innerHTML = "<p><strong>Source:</strong> " + src + "</p>" +
                      "<p><strong>Tokens Used:</strong> " + toks + "</p>" +
                      "<p><strong>LLM Calls:</strong> " + c + "</p>" +
                      "<p><strong>Secrets Types Redacted:</strong> " + rs + "</p>";
    }
  }

  // ------------------------------------------------------------------
  // Data loading
  // ------------------------------------------------------------------
  async function loadData() {
    try {
      const resp = await fetch('../data/results.json');
      DATA = await resp.json();
      init();
    } catch (e) {
      console.error('Failed to load results.json:', e);
      document.getElementById('skeleton').innerHTML =
        '<div class="empty-state">Failed to load data. Run bake_results.py first.</div>';
    }
  }

  function init() {
    buildPRLedger();
    buildScrubber();
    renderImpactPanel();
    selectPR(0);
    document.addEventListener('keydown', handleKeyboard);
  }

  // ------------------------------------------------------------------
  // PR Ledger (left column)
  // ------------------------------------------------------------------
  function buildPRLedger() {
    const tbody = document.getElementById('pr-tbody');
    tbody.innerHTML = '';
    DATA.prs.forEach(function (pr, i) {
      const tr = document.createElement('tr');
      tr.dataset.index = i;
      tr.onclick = function () { selectPR(i); };
      var dateStr = pr.date.split('T')[0];
      var tagHtml = '';
      if (pr.tag === 'HACK') tagHtml = '<span class="tag tag-hack">HACK</span>';
      else if (pr.tag === 'FIX') tagHtml = '<span class="tag tag-fix">FIX</span>';
      else if (pr.tag === 'MOVE') tagHtml = '<span class="tag tag-move">MOVE</span>';
      tr.innerHTML =
        '<td class="pr-num-cell">' + pr.pr + '</td>' +
        '<td class="pr-title-cell">' + escHtml(pr.title) + '</td>' +
        
        '<td class="pr-date-cell">' + dateStr + '</td>'
        ;
      tbody.appendChild(tr);
    });
  }

  // ------------------------------------------------------------------
  // Time scrubber
  // ------------------------------------------------------------------
  function buildScrubber() {
    var scrubber = document.getElementById('scrubber');
    scrubber.max = DATA.prs.length - 1;
    scrubber.value = 0;
    scrubber.addEventListener('input', function () {
      selectPR(parseInt(this.value));
    });

    // Build tick marks
    var ticks = document.getElementById('scrubber-ticks');
    ticks.innerHTML = '';
    DATA.prs.forEach(function (pr, i) {
      var tick = document.createElement('span');
      tick.className = 'scrubber-tick';
      if (pr.tag) tick.className += ' scrubber-tick-plot';
      tick.style.left = (i / (DATA.prs.length - 1) * 100) + '%';
      tick.title = 'PR #' + pr.pr + ': ' + pr.title;
      ticks.appendChild(tick);
    });
  }

  // ------------------------------------------------------------------
  // Select a PR
  // ------------------------------------------------------------------
  window.selectPR = function selectPR(index) {
    currentPRIndex = index;
    var pr = DATA.prs[index];

    // Update scrubber
    document.getElementById('scrubber').value = index;
    document.getElementById('scrubber-label').textContent = 'PR #' + pr.pr + ': ' + pr.title;

    // Update ledger highlighting
    var rows = document.querySelectorAll('#pr-tbody tr');
    rows.forEach(function (r) { r.classList.remove('active'); });
    if (rows[index]) {
      rows[index].classList.add('active');
      rows[index].scrollIntoView({ block: 'nearest' });
    }

    // Show skeleton briefly
    showSkeleton();
    setTimeout(function () {
      hideSkeleton();
      if (currentView === 'pr') renderPRView(pr);
      else renderEditorView(pr);
      renderHacksLedger(pr.pr);
      renderAgentLog(pr);
    }, 200);
  }

  // ------------------------------------------------------------------
  // PR View
  // ------------------------------------------------------------------
  function renderPRView(pr) {
    var view = document.getElementById('pr-view');
    var editor = document.getElementById('editor-view');
    view.style.display = 'block';
    editor.style.display = 'none';
    document.getElementById('empty-state').style.display = 'none';

    var isMerged = mergedPRs.has(pr.pr);

    document.getElementById('pr-title').textContent = pr.title;
    document.getElementById('pr-number').textContent = '#' + pr.pr;
    document.getElementById('pr-branch').textContent = pr.branch + ' \u2192 main';
    document.getElementById('pr-state').textContent = isMerged ? 'MERGED' : 'OPEN';
    document.getElementById('pr-state').className = 'pr-state' + (isMerged ? ' merged' : '');
    document.getElementById('pr-description').textContent = pr.diff ? '' : 'No file changes in this PR.';
    document.getElementById('pr-author').textContent = pr.author;
    document.getElementById('pr-date').textContent = pr.date.split('T')[0];

    // Diff
    renderDiff(pr.diff);

    // Review thread
    renderReviewThread(pr.comments);

    // Merge area
    var mergeArea = document.getElementById('merge-area');
    var mergeBtn = document.getElementById('merge-btn');
    if (isMerged) {
      mergeBtn.disabled = true;
      mergeBtn.textContent = 'Merged';
    } else {
      mergeBtn.disabled = false;
      mergeBtn.textContent = 'Merge';
    }
  }

  function renderDiff(diffText) {
    var block = document.getElementById('diff-block');
    if (!diffText || !diffText.trim()) {
      block.innerHTML = '<div class="diff-empty">No diff available</div>';
      return;
    }

    var lines = diffText.split('\n');
    var html = '';
    var lineNumOld = 0;
    var lineNumNew = 0;

    lines.forEach(function (line) {
      var cls = 'diff-line';
      var numDisplay = '';

      if (line.startsWith('@@')) {
        cls += ' diff-hunk';
        var m = line.match(/@@ -(\d+)/);
        if (m) lineNumOld = parseInt(m[1]) - 1;
        var m2 = line.match(/\+(\d+)/);
        if (m2) lineNumNew = parseInt(m2[1]) - 1;
        numDisplay = '...';
      } else if (line.startsWith('+') && !line.startsWith('+++')) {
        cls += ' added';
        lineNumNew++;
        numDisplay = lineNumNew;
      } else if (line.startsWith('-') && !line.startsWith('---')) {
        cls += ' removed';
        lineNumOld++;
        numDisplay = lineNumOld;
      } else if (line.startsWith('diff ') || line.startsWith('index ') ||
                 line.startsWith('---') || line.startsWith('+++')) {
        cls += ' diff-meta';
        numDisplay = '';
      } else {
        lineNumOld++;
        lineNumNew++;
        numDisplay = lineNumNew;
      }

      html += '<div class="' + cls + '">' +
        '<span class="diff-line-num">' + numDisplay + '</span>' +
        '<span class="diff-line-text">' + escHtml(line) + '</span>' +
        '</div>';
    });

    block.innerHTML = html;
  }

  function renderReviewThread(comments) {
    var thread = document.getElementById('review-thread');
    if (!comments || comments.length === 0) {
      thread.innerHTML = '';
      return;
    }

    var html = '<h3 class="thread-title">Review</h3>';

    comments.forEach(function (c) {
      var kindLabel = c.kind.replace('_', ' ');
      var kindClass = 'comment-kind-' + c.kind;

      html += '<div class="review-comment ' + kindClass + '">';
      html += '<div class="review-comment-header">';
      html += '<span class="review-author">CodeMemory</span>';
      html += '<span class="comment-kind">' + kindLabel + '</span>';
      html += '</div>';

      if (c.anchor_snippet) {
        html += '<div class="comment-anchor"><code>' + escHtml(c.anchor_snippet.split('\n')[0]) + '</code></div>';
      }

      html += '<div class="comment-body">' + markdownToHtml(c.body_md) + '</div>';

      // Checker details
      if (c.checker) {
        html += '<div class="checker-details">';
        html += '<div class="checker-verdict">';
        html += 'Verdict: <strong>' + c.checker.verdict + '</strong>';
        html += ' (confidence: ' + (c.checker.confidence * 100).toFixed(0) + '%)';
        html += '</div>';
        if (c.checker.counter_arguments && c.checker.counter_arguments.length) {
          html += '<div class="checker-counter">';
          html += '<strong>Counter-arguments considered:</strong><ul>';
          c.checker.counter_arguments.forEach(function (ca) {
            html += '<li>' + escHtml(ca) + '</li>';
          });
          html += '</ul></div>';
        }
        html += '</div>';
      }

      // SQL baseline
      if (c.sql_baseline) {
        html += '<div class="sql-baseline">';
        html += '<strong>SQL baseline</strong> (what a ticket-ID join returns):<br>';
        html += '<code>' + escHtml(c.sql_baseline.query) + '</code>';
        if (c.sql_baseline.rows && c.sql_baseline.rows.length) {
          html += '<div class="sql-rows">' + JSON.stringify(c.sql_baseline.rows) + '</div>';
        } else {
          html += '<div class="sql-rows sql-empty">0 rows (no shared ticket)</div>';
        }
        html += '</div>';
      }

      // Suggestion block
      if (c.suggestion) {
        html += '<div class="suggestion-block">';
        html += '<div class="suggestion-header">Suggestion</div>';
        html += '<p><strong>' + escHtml(c.suggestion.summary) + '</strong></p>';
        html += '<p>' + escHtml(c.suggestion.proposal) + '</p>';
        html += '<p>Affected: ' + c.suggestion.hack_ids.join(', ') + '</p>';
        html += '<div class="suggestion-actions">';
        html += '<button class="suggestion-btn" disabled>Dismiss</button>';
        html += '<button class="suggestion-btn" disabled>Open issue</button>';
        html += '</div></div>';
      }

      html += '</div>';
    });

    thread.innerHTML = html;
  }

  // ------------------------------------------------------------------
  // Merge
  // ------------------------------------------------------------------
  window.mergePR = function mergePR() {
    var pr = DATA.prs[currentPRIndex];
    mergedPRs.add(pr.pr);
    document.getElementById('pr-state').textContent = 'MERGED';
    document.getElementById('pr-state').className = 'pr-state merged';
    document.getElementById('merge-btn').disabled = true;
    document.getElementById('merge-btn').textContent = 'Merged';

    // Add "Retained to memory" to log
    addLogEntry('retain', 'Retained to memory');
  }

  // ------------------------------------------------------------------
  // Editor View
  // ------------------------------------------------------------------
  function renderEditorView(pr) {
    var view = document.getElementById('editor-view');
    var prView = document.getElementById('pr-view');
    view.style.display = 'block';
    prView.style.display = 'none';
    document.getElementById('empty-state').style.display = 'none';

    // Determine which files to show
    var hacksAtPR = getHacksAtPR(pr.pr);
    var files = pr.files_after || {};
    var allFiles = getAllFilesAtPR(pr.pr);

    // If no files with hacks, show a generic file
    if (Object.keys(files).length === 0 && Object.keys(allFiles).length === 0) {
      view.innerHTML = '<div class="empty-state">No tracked files at this point in the timeline.</div>';
      return;
    }

    // Build file explorer
    var sidebar = document.getElementById('editor-sidebar');
    var sidebarHtml = '';
    var displayFiles = Object.keys(files).length > 0 ? files : allFiles;
    var firstFile = Object.keys(displayFiles)[0];

    Object.keys(displayFiles).sort().forEach(function (fpath) {
      var indent = (fpath.match(/\//g) || []).length;
      var cls = 'sidebar-file';
      if (fpath === firstFile) cls += ' active';
      sidebarHtml += '<div class="' + cls + '" style="padding-left:' + (8 + indent * 12) + 'px" ' +
        'onclick="window._showEditorFile(\'' + escAttr(fpath) + '\')">' +
        fpath.split('/').pop() + '</div>';
    });
    sidebar.innerHTML = sidebarHtml;

    // Show first file
    if (firstFile) {
      showEditorFile(firstFile, displayFiles, hacksAtPR, pr);
    }

    // Update status bar
    document.getElementById('editor-branch').textContent = pr.branch;
  }

  function showEditorFile(fpath, files, hacksAtPR, pr) {
    var content = files[fpath] || '';
    var titlebar = document.getElementById('editor-titlebar');
    titlebar.textContent = fpath;

    var tabs = document.getElementById('editor-tabs');
    tabs.innerHTML = '<span class="editor-tab active">' + fpath.split('/').pop() + '</span>';

    var editorContent = document.getElementById('editor-content');
    var lines = content.split('\n');
    var html = '';

    // Find hacks anchored in this file
    var fileHacks = hacksAtPR.filter(function (h) {
      var loc = getHackLocation(h, pr.pr);
      return loc.path === fpath;
    });

    lines.forEach(function (line, idx) {
      var lineNum = idx + 1;
      var isHackLine = false;
      var hackForLine = null;

      // Check if this line is part of a hack anchor
      fileHacks.forEach(function (h) {
        var snippetLines = h.anchor_snippet.split('\n');
        snippetLines.forEach(function (sl) {
          if (sl.trim() && line.trim() === sl.trim()) {
            isHackLine = true;
            hackForLine = h;
          }
        });
      });

      // Syntax highlighting (minimal)
      var highlighted = syntaxHighlight(line);

      var lineClass = 'editor-line';
      if (isHackLine) lineClass += ' hack-line';

      html += '<div class="' + lineClass + '">';
      html += '<span class="editor-line-num">' + lineNum + '</span>';
      html += '<span class="editor-line-text">' + highlighted + '</span>';

      // Check if function def with hack underline
      if (isHackLine && hackForLine && /def\s+\w+/.test(line)) {
        // The underline is applied via CSS on .hack-line
      }

      html += '</div>';

      // Hover card after the function line containing the hack
      if (hackForLine && /def\s+\w+/.test(line)) {
        var loc = getHackLocation(hackForLine, pr.pr);
        html += '<div class="hover-card" data-hack="' + hackForLine.id + '">';
        html += '<div class="hover-card-title">' + escHtml(hackForLine.what) + '</div>';
        html += '<div class="hover-card-field"><strong>Why:</strong> ' + escHtml(hackForLine.why) + '</div>';
        html += '<div class="hover-card-field"><strong>Risk:</strong> ' + hackForLine.risk + '</div>';
        html += '<div class="hover-card-field"><strong>Revisit:</strong> ' + escHtml(hackForLine.revisit_condition) + '</div>';
        html += '<div class="hover-card-field"><strong>Added by:</strong> ' +
          escHtml(DATA.prs.find(function(p) { return p.pr === hackForLine.pr_added; })?.author || '') +
          ' in PR #' + hackForLine.pr_added + '</div>';
        html += '<div class="hover-card-field"><strong>Status:</strong> ' + hackForLine.status + '</div>';
        html += '</div>';
      }
    });

    editorContent.innerHTML = html;

    // Trigger hover card appearance after delay
    setTimeout(function () {
      var cards = editorContent.querySelectorAll('.hover-card');
      cards.forEach(function (card) {
        card.classList.add('visible');
      });
    }, 600);
  }

  // Expose for onclick
  window._showEditorFile = function (fpath) {
    var pr = DATA.prs[currentPRIndex];
    var hacksAtPR = getHacksAtPR(pr.pr);
    var files = pr.files_after || {};
    showEditorFile(fpath, files, hacksAtPR, pr);
  };

  function syntaxHighlight(line) {
    var escaped = escHtml(line);
    // Keywords
    escaped = escaped.replace(
      /\b(def|class|import|from|return|if|else|elif|for|while|try|except|with|as|raise|global|not|and|or|in|is|None|True|False|self)\b/g,
      '<span class="kw">$1</span>'
    );
    // Comments
    escaped = escaped.replace(/(#.*)$/, '<span class="cm">$1</span>');
    // Strings
    escaped = escaped.replace(/(&quot;[^&]*&quot;|&#x27;[^&]*&#x27;)/g, '<span class="st">$1</span>');
    return escaped;
  }

  // ------------------------------------------------------------------
  // Hacks Ledger (right column)
  // ------------------------------------------------------------------
  function getHacksAtPR(prNum) {
    return DATA.hacks.filter(function (h) {
      return h.pr_added <= prNum;
    }).map(function (h) {
      // Compute status at this PR
      var status = 'open';
      if (h.status_since_pr <= prNum) {
        status = h.status;
      } else {
        // Check timeline
        status = 'open';
      }
      return Object.assign({}, h, { _status_at: status });
    });
  }

  function getHackLocation(hack, prNum) {
    var loc = hack.location_by_pr;
    var best = { path: hack.path_at_add, function: hack.function_at_add };
    var bestPR = 0;
    Object.keys(loc).forEach(function (pr) {
      var n = parseInt(pr);
      if (n <= prNum && n > bestPR) {
        bestPR = n;
        best = loc[pr];
      }
    });
    return best;
  }

  function renderHacksLedger(prNum) {
    var list = document.getElementById('hacks-list');
    var hacks = getHacksAtPR(prNum);

    if (hacks.length === 0) {
      list.innerHTML = '<div class="empty-state">No hacks tracked yet.</div>';
      return;
    }

    var html = '';
    hacks.forEach(function (h) {
      var status = h._status_at;
      var statusClass = (status === 'open') ? 'status-open' : 'status-resolved';
      var loc = getHackLocation(h, prNum);

      // Calculate age
      var addedDate = DATA.prs.find(function(p) { return p.pr === h.pr_added; });
      var currentDate = DATA.prs.find(function(p) { return p.pr === prNum; });
      var age = '';
      if (addedDate && currentDate) {
        var d1 = new Date(addedDate.date);
        var d2 = new Date(currentDate.date);
        var days = Math.floor((d2 - d1) / (1000 * 60 * 60 * 24));
        age = days > 30 ? Math.floor(days / 30) + ' months' : days + ' days';
      }

      html += '<div class="hack-row">';
      html += '<div class="hack-id">' + h.id + '</div>';
      html += '<div class="hack-what">' + escHtml(h.what) + '</div>';
      html += '<div class="hack-details">';
      html += '<span class="hack-risk risk-' + h.risk + '">' + h.risk + '</span>';
      html += '<span class="hack-status ' + statusClass + '">' + status.replace('_', ' ') + '</span>';
      html += '</div>';
      html += '<div class="hack-revisit">' + escHtml(h.revisit_condition) + '</div>';
      if (age) html += '<div class="hack-age">' + age + '</div>';
      html += '<div class="hack-location">' + escHtml(loc.path) + '</div>';
      html += '</div>';
    });

    list.innerHTML = html;
  }

  // ------------------------------------------------------------------
  // Agent Log
  // ------------------------------------------------------------------
  function renderAgentLog(pr) {
    var container = document.getElementById('log-entries');
    container.innerHTML = '';

    if (!pr.log || pr.log.length === 0) return;

    pr.log.forEach(function (entry, i) {
      var div = document.createElement('div');
      div.className = 'log-entry';
      div.style.opacity = '0';
      div.textContent = pr.date.split('T')[0] + ' ' + entry.kind + ': ' + entry.text;
      container.appendChild(div);

      // Reveal with delay
      setTimeout(function () {
        div.style.opacity = '1';
      }, i * 350);
    });
  }

  function addLogEntry(kind, text) {
    var container = document.getElementById('log-entries');
    var pr = DATA.prs[currentPRIndex];
    var div = document.createElement('div');
    div.className = 'log-entry';
    div.textContent = pr.date.split('T')[0] + ' ' + kind + ': ' + text;
    container.appendChild(div);
  }

  // ------------------------------------------------------------------
  // View switching
  // ------------------------------------------------------------------
  function switchView(view) {
    currentView = view;
    document.querySelectorAll('.view-tab').forEach(function (t) {
      t.classList.toggle('active', t.dataset.view === view);
    });
    var pr = DATA.prs[currentPRIndex];
    if (view === 'pr') renderPRView(pr);
    else renderEditorView(pr);
  }
  window.switchView = switchView;

  // ------------------------------------------------------------------
  // Skeleton / empty state
  // ------------------------------------------------------------------
  function showSkeleton() {
    document.getElementById('skeleton').style.display = 'block';
    document.getElementById('pr-view').style.display = 'none';
    document.getElementById('editor-view').style.display = 'none';
    document.getElementById('empty-state').style.display = 'none';
  }

  function hideSkeleton() {
    document.getElementById('skeleton').style.display = 'none';
  }

  // ------------------------------------------------------------------
  // Keyboard navigation
  // ------------------------------------------------------------------
  function handleKeyboard(e) {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      if (currentPRIndex < DATA.prs.length - 1) selectPR(currentPRIndex + 1);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (currentPRIndex > 0) selectPR(currentPRIndex - 1);
    }
  }

  // ------------------------------------------------------------------
  // Get all files at a given PR
  // ------------------------------------------------------------------
  function getAllFilesAtPR(prNum) {
    // Build cumulative file state
    var files = {};
    for (var i = 0; i < DATA.prs.length; i++) {
      var pr = DATA.prs[i];
      if (pr.pr > prNum) break;
      var fa = pr.files_after || {};
      Object.keys(fa).forEach(function (k) {
        files[k] = fa[k];
      });
    }
    return files;
  }

  // ------------------------------------------------------------------
  // Drawers and Modals
  // ------------------------------------------------------------------
  window.openDrawer = function (id) {
    document.getElementById('drawer-' + id).classList.add('open');
    var overlay = document.getElementById('drawer-overlay');
    if (overlay) overlay.classList.add('open');
  };
  window.closeDrawer = function () {
    document.querySelectorAll('.drawer').forEach(function (d) {
      d.classList.remove('open');
    var overlay = document.getElementById('drawer-overlay');
    if (overlay) overlay.classList.remove('open');
    });
  };
  window.openModal = function (id) {
    document.getElementById('modal-' + id).style.display = 'flex';
  };
  window.closeModal = function (id) {
    document.getElementById('modal-' + id).style.display = 'none';
  };

  // Close on overlay click
  document.addEventListener('click', function (e) {
    if (e.target.classList.contains('modal-overlay')) {
      e.target.style.display = 'none';
    }
  });

  // ------------------------------------------------------------------
  // Guided Run
  // ------------------------------------------------------------------
  var guidedSteps = [
    { pr: 6, view: 'pr', caption: 'PR #6: A workaround is introduced. Fixed 3-second retry delay for Stripe rate limiting.', merge: true },
    { pr: 6, view: 'editor', caption: 'Editor: Hover card shows what the hack is, why it exists, and when to remove it.' },
    { pr: 17, view: 'pr', caption: 'PR #17: File renamed. CodeMemory tracks the hack to its new location.' },
    { pr: 17, view: 'editor', caption: 'Editor: The hover card appears on the renamed function.' },
    { pr: 22, view: 'pr', caption: 'PR #22: Third Stripe hack triggers root-cause suggestion.' },
    { pr: 24, view: 'pr', caption: 'PR #24: Stripe SDK upgrade resolves the retry workaround. No shared ticket, file, or wording.' },
    { pr: 26, view: 'pr', caption: 'PR #26: Workaround code removed. Hack marked as retired.' },
  ];
  var guidedIndex = 0;

  window.startGuidedRun = function () {
    guidedRunning = true;
    guidedPaused = false;
    guidedIndex = 0;
    document.getElementById('guided-bar').style.display = 'flex';
    runGuidedStep();
  };

  window.stopGuidedRun = function () {
    guidedRunning = false;
    guidedPaused = false;
    clearTimeout(guidedTimer);
    document.getElementById('guided-bar').style.display = 'none';
  };

  window.toggleGuidedPause = function () {
    guidedPaused = !guidedPaused;
    document.getElementById('guided-pause').textContent = guidedPaused ? 'Resume' : 'Pause';
    if (!guidedPaused) runGuidedStep();
  };

  function runGuidedStep() {
    if (!guidedRunning || guidedPaused || guidedIndex >= guidedSteps.length) {
      if (guidedIndex >= guidedSteps.length) window.stopGuidedRun();
      return;
    }

    var step = guidedSteps[guidedIndex];
    document.getElementById('guided-caption').textContent = step.caption;

    // Find PR index
    var idx = DATA.prs.findIndex(function (p) { return p.pr === step.pr; });
    if (idx >= 0) {
      selectPR(idx);
      if (step.view) switchView(step.view);
      if (step.merge) {
        setTimeout(function () { mergePR(); }, 2000);
      }
    }

    guidedIndex++;
    guidedTimer = setTimeout(runGuidedStep, 6000);
  }

  // ------------------------------------------------------------------
  // Utilities
  // ------------------------------------------------------------------
  function escHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
  }

  function escAttr(str) {
    return str.replace(/'/g, "\\'").replace(/"/g, '\\"');
  }

  function markdownToHtml(md) {
    if (!md) return '';
    // Simple markdown: **bold**, `code`, newlines, - lists
    var html = escHtml(md);
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    html = html.replace(/\n\n/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');
    return '<p>' + html + '</p>';
  }

  // ------------------------------------------------------------------
  // Boot
  // ------------------------------------------------------------------
  loadData();
})();
