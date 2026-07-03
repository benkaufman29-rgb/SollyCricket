let autoplayInterval = null;
let isPythonReady = false;
const COMMENTARY_PAGE_SIZE = 30;
let commentaryPage = 0;

// Initialize Webview connection
window.addEventListener('pywebviewready', () => {
    isPythonReady = true;
    if (window.pywebview && window.pywebview.api) {
        // Load the logo into the start screen
        window.pywebview.api.get_logo().then(dataUri => {
            document.getElementById('start-logo').src = dataUri || '';
        });
    }
});

function startMatch() {
    // Hide the start screen overlay
    const overlay = document.getElementById('start-overlay');
    overlay.classList.add('hidden');
    // After the fade transition, remove from DOM
    setTimeout(() => {
        overlay.style.display = 'none';
    }, 600);
    // Load the match state
    loadMatchState();
}

// Fallback in case we are testing in a standard browser
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        if (!isPythonReady) {
            console.log("pywebview API not detected, running in mock demo mode");
        }
    }, 1000);
});

function loadMatchState() {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.get_state().then(updateUI);
    }
}

function bowlBall() {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.step_ball().then(updateUI);
    }
}

function toggleAutoplay() {
    const btn = document.getElementById('btn-autoplay');
    if (autoplayInterval) {
        clearTimeout(autoplayInterval);
        autoplayInterval = null;
        btn.innerText = "Start Autoplay";
        btn.classList.remove('active');
    } else {
        btn.innerText = "Stop Autoplay";
        btn.classList.add('active');
        autoplayInterval = true;  // sentinel — not a timer ID
        doAutoplay();
    }
}

function doAutoplay() {
    if (!autoplayInterval) return;  // User stopped autoplay
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.step_ball().then(state => {
            // IMPORTANT: user may have pressed Stop while this promise was
            // in flight — don't re-schedule if autoplay is cancelled.
            if (!autoplayInterval) return;
            updateUI(state);
            const innings = state.innings_number === 1 ? state.innings1 : state.innings2;
            if (innings.is_completed) {
                toggleAutoplay();
            } else {
                // Schedule next ball only after this one completes
                autoplayInterval = setTimeout(doAutoplay, 1200);
            }
        });
    }
}

function startSecondInnings() {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.start_second_innings().then(updateUI);
    }
}

function resetMatch() {
    if (autoplayInterval) {
        toggleAutoplay();
    }
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.reset_match().then(updateUI);
    }
}

function olderCommentary() {
    commentaryPage++;
    // Re-render with the current state (stale state is fine, commentary is already stored)
    const state = window._lastState;
    if (state) renderCommentary(state);
}

function newerCommentary() {
    commentaryPage = Math.max(0, commentaryPage - 1);
    const state = window._lastState;
    if (state) renderCommentary(state);
}

function updateUI(state) {
    window._lastState = state;
    // Reset to most recent page when new data arrives from backend
    commentaryPage = 0;
    if (!state) return;

    const innings = state.innings_number === 1 ? state.innings1 : state.innings2;
    if (!innings) return;

    // 1. Update Match Header
    document.getElementById('header-batting-team').innerText = innings.batting_team_name;
    document.getElementById('header-score').innerText = `${innings.score}/${innings.wickets}`;
    document.getElementById('header-overs').innerText = `(${innings.overs_str} Ov)`;

    const oversFloat = Math.floor(innings.balls_bowled / 6) + (innings.balls_bowled % 6) / 6.0;
    const crr = oversFloat > 0 ? (innings.score / oversFloat).toFixed(2) : "0.00";
    document.getElementById('header-crr').innerText = `CRR: ${crr}`;

    const targetEl = document.getElementById('header-target');
    if (innings.target) {
        targetEl.style.display = 'inline-block';
        targetEl.innerText = `Target: ${innings.target}`;
    } else {
        targetEl.style.display = 'none';
    }

    document.getElementById('header-status').innerText = state.status_message;

    // Innings switch button display
    const btnInnings = document.getElementById('btn-innings');
    const btnBowl = document.getElementById('btn-bowl');
    if (state.innings_number === 1 && innings.is_completed) {
        btnInnings.style.display = 'inline-block';
        btnBowl.style.display = 'none';
    } else if (state.innings_number === 2 && innings.is_completed) {
        btnInnings.style.display = 'none';
        btnBowl.style.display = 'none';
    } else {
        btnInnings.style.display = 'none';
        btnBowl.style.display = 'inline-block';
    }

    // 2. Update Batting Scorecard
    document.getElementById('batting-team-title').innerText = `Batting: ${innings.batting_team_name}`;
    const battingTbody = document.getElementById('batting-tbody');
    battingTbody.innerHTML = '';

    innings.batting_card.forEach(player => {
        let statusHTML = "";
        if (player.status === "dnb") {
            statusHTML = "did not bat";
        } else if (player.status === "batting") {
            statusHTML = "batting" + (innings.striker && innings.striker.name === player.name ? " *" : "");
        } else if (player.status === "out") {
            // Show dismissal mode + commentary description
            statusHTML = `<span class="dismissal-mode">${player.dismissal || 'out'}</span>`;
            if (player.dismissal_description) {
                statusHTML += `<br><span class="dismissal-desc">${player.dismissal_description}</span>`;
            }
        } else {
            statusHTML = player.dismissal || "out";
        }

        const isStriker = innings.striker && innings.striker.name === player.name;
        const isNonStriker = innings.non_striker && innings.non_striker.name === player.name;

        let rowClass = "";
        if (isStriker) rowClass = "striker-active";
        else if (isNonStriker) rowClass = "non-striker-active";

        const row = document.createElement('tr');
        if (rowClass) row.className = rowClass;

        row.innerHTML = `
            <td>${player.name}</td>
            <td class="dismissal-col">${statusHTML}</td>
            <td class="num-col">${player.status !== 'dnb' ? player.runs_scored : '-'}</td>
            <td class="num-col">${player.status !== 'dnb' ? player.balls_faced : '-'}</td>
            <td class="num-col">${player.status !== 'dnb' ? player.fours : '-'}</td>
            <td class="num-col">${player.status !== 'dnb' ? player.sixes : '-'}</td>
            <td class="num-col">${player.status !== 'dnb' ? player.strike_rate.toFixed(1) : '-'}</td>
        `;
        battingTbody.appendChild(row);
    });

    // Extras
    document.getElementById('extras-details').innerText = `(w ${innings.extras.wides}, nb ${innings.extras.noballs}, b ${innings.extras.byes}, lb ${innings.extras.legbyes})`;
    document.getElementById('extras-total').innerText = innings.total_extras;

    // 3. Update Bowling Scorecard
    document.getElementById('bowling-team-title').innerText = `Bowling: ${innings.bowling_team_name}`;
    const bowlingTbody = document.getElementById('bowling-tbody');
    bowlingTbody.innerHTML = '';

    innings.bowling_card.forEach(player => {
        const isCurrent = innings.current_bowler && innings.current_bowler.name === player.name;
        const row = document.createElement('tr');
        if (isCurrent) row.className = "striker-active";

        row.innerHTML = `
            <td>${player.name}${isCurrent ? ' *' : ''}</td>
            <td class="num-col">${player.overs_bowled}</td>
            <td class="num-col">${player.maidens}</td>
            <td class="num-col">${player.runs_conceded}</td>
            <td class="num-col">${player.wickets_taken}</td>
            <td class="num-col">${player.economy_rate.toFixed(2)}</td>
        `;
        bowlingTbody.appendChild(row);
    });

    // 4. Update Fall of Wickets (condensed text)
    const condensedFOW = document.getElementById('condensed-fow');
    if (innings.fall_of_wickets.length === 0) {
        condensedFOW.innerText = "No wickets fallen yet.";
    } else {
        condensedFOW.innerHTML = innings.fall_of_wickets.map(fow =>
            `${fow.wicket}/${fow.score} (${fow.player})`
        ).join(', ');
    }

    // 5. Show first innings scorecards if we're in innings 2
    const firstInningsContainer = document.getElementById('first-innings-container');
    if (state.innings_number === 2 && state.innings1) {
        // Clear and show the container
        firstInningsContainer.style.display = 'block';
        firstInningsContainer.innerHTML = `
            <div class="innings-separator"><span>INNINGS 1</span></div>
            ${buildScorecardsHTML(state.innings1, '1')}
        `;
    } else {
        firstInningsContainer.style.display = 'none';
    }

    // 6. Update Commentary Feed (with pagination)
    renderCommentary(state);
}

/**
 * Build full scorecard HTML (batting + bowling + FOW) for a given innings.
 */
function buildScorecardsHTML(innings, inningsLabel) {
    if (!innings) return '';

    // Batting table rows
    let battingRows = '';
    innings.batting_card.forEach(player => {
        let statusHTML = '';
        if (player.status === 'dnb') {
            statusHTML = 'did not bat';
        } else if (player.status === 'batting') {
            statusHTML = 'batting *';
        } else if (player.status === 'out') {
            statusHTML = `<span class="dismissal-mode">${player.dismissal || 'out'}</span>`;
            if (player.dismissal_description) {
                statusHTML += `<br><span class="dismissal-desc">${player.dismissal_description}</span>`;
            }
        } else if (player.status === 'not out') {
            statusHTML = 'not out';
        } else {
            statusHTML = player.dismissal || '';
        }

        battingRows += `<tr>
            <td>${player.name}</td>
            <td class="dismissal-col">${statusHTML}</td>
            <td class="num-col">${player.status !== 'dnb' ? player.runs_scored : '-'}</td>
            <td class="num-col">${player.status !== 'dnb' ? player.balls_faced : '-'}</td>
            <td class="num-col">${player.status !== 'dnb' ? player.fours : '-'}</td>
            <td class="num-col">${player.status !== 'dnb' ? player.sixes : '-'}</td>
            <td class="num-col">${player.status !== 'dnb' ? player.strike_rate.toFixed(1) : '-'}</td>
        </tr>`;
    });

    // Extras
    const extras = innings.extras || { wides: 0, noballs: 0, byes: 0, legbyes: 0 };
    const extrasHTML = `(w ${extras.wides}, nb ${extras.noballs}, b ${extras.byes}, lb ${extras.legbyes})`;

    // Bowling table rows
    let bowlingRows = '';
    innings.bowling_card.forEach(player => {
        bowlingRows += `<tr>
            <td>${player.name}</td>
            <td class="num-col">${player.overs_bowled}</td>
            <td class="num-col">${player.maidens}</td>
            <td class="num-col">${player.runs_conceded}</td>
            <td class="num-col">${player.wickets_taken}</td>
            <td class="num-col">${player.economy_rate.toFixed(2)}</td>
        </tr>`;
    });

    // FOW
    let fowHTML = '';
    if (innings.fall_of_wickets.length === 0) {
        fowHTML = 'No wickets fallen.';
    } else {
        fowHTML = innings.fall_of_wickets.map(fow =>
            `${fow.wicket}/${fow.score} (${fow.player})`
        ).join(', ');
    }

    return `
        <div class="card batting-card">
            <h3 class="card-title">Batting: ${innings.batting_team_name}</h3>
            <table class="cric-table">
                <thead>
                    <tr>
                        <th>Batsman</th>
                        <th>Dismissal</th>
                        <th class="num-col">R</th>
                        <th class="num-col">B</th>
                        <th class="num-col">4s</th>
                        <th class="num-col">6s</th>
                        <th class="num-col">SR</th>
                    </tr>
                </thead>
                <tbody>${battingRows}</tbody>
            </table>
            <div class="extras-row">
                <strong>Extras:</strong> <span>${extrasHTML}</span> <span class="extras-total">${innings.total_extras || 0}</span>
            </div>
        </div>
        <div class="card bowling-card">
            <h3 class="card-title">Bowling: ${innings.bowling_team_name}</h3>
            <table class="cric-table">
                <thead>
                    <tr>
                        <th>Bowler</th>
                        <th class="num-col">O</th>
                        <th class="num-col">M</th>
                        <th class="num-col">R</th>
                        <th class="num-col">W</th>
                        <th class="num-col">Econ</th>
                    </tr>
                </thead>
                <tbody>${bowlingRows}</tbody>
            </table>
        </div>
        <div class="card fow-card">
            <h3 class="card-title">Fall of Wickets</h3>
            <div class="condensed-fow">${fowHTML}</div>
        </div>
    `;
}

function renderCommentary(state) {
    // Build combined commentary array from both innings when in innings 2
    let allComms = [];

    if (state.innings_number === 2 && state.innings1 && state.innings2) {
        const inns1 = (state.innings1.commentary || []).map(c => ({...c, innings: 1}));
        const inns2 = (state.innings2.commentary || []).map(c => ({...c, innings: 2}));
        allComms = [...inns1, ...inns2];  // Chronological: all of innings 1, then all of innings 2
    } else {
        const innings = state.innings_number === 1 ? state.innings1 : state.innings2;
        if (!innings) return;
        allComms = (innings.commentary || []).map(c => ({...c, innings: state.innings_number}));
    }

    const feed = document.getElementById('commentary-feed');
    feed.innerHTML = '';

    // Calculate ball stamps per innings (reset counter at innings boundary)
    let legalBalls = 0;
    let currentInnings = allComms.length > 0 ? allComms[0].innings : 1;
    for (let i = 0; i < allComms.length; i++) {
        let outcome = allComms[i];
        if (outcome.innings !== currentInnings) {
            legalBalls = 0;
            currentInnings = outcome.innings;
        }
        let overNum = Math.floor(legalBalls / 6);
        let ballNum = (legalBalls % 6) + 1;
        outcome.ball_stamp = `${overNum}.${ballNum}`;

        if (outcome.extra_type !== 'w' && outcome.extra_type !== 'nb') {
            legalBalls++;
        }
    }

    // Determine which slice to show based on current page
    const totalPages = Math.ceil(allComms.length / COMMENTARY_PAGE_SIZE);
    commentaryPage = Math.min(commentaryPage, totalPages - 1);
    commentaryPage = Math.max(0, commentaryPage);

    const endIdx = allComms.length - commentaryPage * COMMENTARY_PAGE_SIZE;
    const startIdx = Math.max(0, endIdx - COMMENTARY_PAGE_SIZE);
    const pageComms = allComms.slice(startIdx, endIdx);

    // Display in reverse order (newest first within the page)
    const reversedComms = pageComms.reverse();

    // "Load Newer" button (top of feed, only if not on most recent page)
    if (commentaryPage > 0) {
        const newerBtn = document.createElement('button');
        newerBtn.className = 'comm-page-btn newer-btn';
        newerBtn.innerText = '← Newer Commentary';
        newerBtn.onclick = newerCommentary;
        feed.appendChild(newerBtn);
    }

    // Track last innings for inserting dividers
    let lastInnings = null;

    // Commentary items
    reversedComms.forEach(outcome => {
        // Insert innings divider when switching between innings in the feed
        if (lastInnings !== null && outcome.innings !== lastInnings) {
            const divider = document.createElement('div');
            divider.className = 'comm-innings-divider';
            const innsLabel = outcome.innings === 1 ? 'INNINGS 1' : 'INNINGS 2';
            divider.innerHTML = `<span>${innsLabel}</span>`;
            feed.appendChild(divider);
        }
        lastInnings = outcome.innings;

        const commItem = document.createElement('div');
        commItem.className = 'comm-item';

        let bubbleClass = "runs-0";
        let bubbleText = outcome.runs.toString();

        if (outcome.is_wicket) {
            bubbleClass = "wicket";
            bubbleText = "W";
        } else if (outcome.extra_type) {
            bubbleClass = "extra";
            bubbleText = outcome.extra_type.toUpperCase();
        } else if (outcome.runs === 4) {
            bubbleClass = "runs-4";
        } else if (outcome.runs === 6) {
            bubbleClass = "runs-6";
        } else if (outcome.runs > 0) {
            bubbleClass = `runs-1`;
        }

        const batsmanFirst = outcome.batsman_name || '';
        const bowlerFirst = outcome.bowler_name || '';
        const description = outcome.description || '';

        // Show innings badge on items from the older innings
        const showBadge = outcome.innings === 1 && state.innings_number === 2;
        const ballHTML = showBadge
            ? `<span class="comm-innings-badge">Inn 1</span>${outcome.ball_stamp}`
            : outcome.ball_stamp;

        commItem.innerHTML = `
            <div class="comm-ball">${ballHTML}</div>
            <div class="comm-bubble ${bubbleClass}">${bubbleText}</div>
            <div class="comm-text-container">
                <div class="comm-title">${bowlerFirst} to ${batsmanFirst}</div>
                <div class="comm-body">${description}</div>
            </div>
        `;
        feed.appendChild(commItem);
    });

    // "Load Older" button (bottom of feed, only if more entries exist)
    if (startIdx > 0) {
        const olderBtn = document.createElement('button');
        olderBtn.className = 'comm-page-btn older-btn';
        olderBtn.innerText = 'Older Commentary →';
        olderBtn.onclick = olderCommentary;
        feed.appendChild(olderBtn);
    }

    // Update page indicator
    const pageIndicator = document.getElementById('commentary-page-info');
    if (pageIndicator) {
        if (allComms.length > COMMENTARY_PAGE_SIZE) {
            const pageNum = commentaryPage + 1;
            pageIndicator.innerText = `Page ${pageNum} of ${totalPages}`;
            pageIndicator.style.display = 'block';
        } else {
            pageIndicator.style.display = 'none';
        }
    }
}