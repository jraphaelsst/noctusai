
        // ─── Ver Pesquisa de Perfil Viral ───────────────────────────────────────

        let _pvsItems = [];
        let _pvsSelectedKeys = new Set(); // chave: "resultId_variableId"

        async function openProfileViralSearch(profile, engReversaSearchId) {
            const modal = new bootstrap.Modal(document.getElementById('profileViralSearchModal'));

            document.getElementById('pvs-profile-name').textContent = '@' + profile;
            document.getElementById('pvs-loading').style.display = 'flex';
            document.getElementById('pvs-empty').style.display = 'none';
            document.getElementById('pvs-content').style.display = 'none';
            document.getElementById('pvs-save-btn').style.display = 'none';
            document.getElementById('pvs-selected-count').textContent = '0';
            document.getElementById('pvs-select-all-label').textContent = 'Selecionar todos';
            _pvsItems = [];
            _pvsSelectedKeys = new Set();

            modal.show();

            try {
                const res = await fetch(`/dashboard/user/searches/profile-viral-search/${engReversaSearchId}`, {
                    headers: { 'Accept': 'application/json' }
                });
                const data = await res.json();

                document.getElementById('pvs-loading').style.display = 'none';

                if (!data.success || !data.data || data.data.length === 0) {
                    document.getElementById('pvs-empty').style.display = 'block';
                    return;
                }

                _pvsItems = data.data;
                renderPvsItems(_pvsItems);
                const totalItems = _pvsItems.reduce((s, g) => s + g.items.length, 0);
                document.getElementById('pvs-count').textContent =
                    `${_pvsItems.length} variável(is) · ${totalItems} item(s)`;
                document.getElementById('pvs-content').style.display = 'block';

            } catch (e) {
                document.getElementById('pvs-loading').style.display = 'none';
                document.getElementById('pvs-empty').style.display = 'block';
                toastr.error('Erro ao carregar a pesquisa.');
            }
        }

        function truncateHeadline(headline, value) {
            if (!headline) return headline;

            const escaped = (value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const valueMatch = escaped ? new RegExp(escaped, 'i').exec(headline) : null;

            // Sem valor localizado: retorna headline inteira
            if (!valueMatch) return headline;

            const valueStart = valueMatch.index;
            const valueEnd   = valueStart + valueMatch[0].length;

            // Corte à ESQUERDA: última pontuação antes do valor
            const beforeValue = headline.slice(0, valueStart);
            const lastPunctMatch = [...beforeValue.matchAll(/[.?!]/g)].pop();
            const leftCut = lastPunctMatch
                ? lastPunctMatch.index + 1   // começa após a pontuação
                : 0;                          // sem pontuação antes → começa do início

            // Corte à DIREITA: primeira pontuação após max(valueEnd, leftCut+30)
            const minRight = Math.max(valueEnd, leftCut + 30);
            const rightRegex = /[.?!]/g;
            rightRegex.lastIndex = minRight;
            const rightMatch = rightRegex.exec(headline);
            const rightCut = rightMatch ? rightMatch.index + 1 : headline.length;

            return headline.slice(leftCut, rightCut).trimStart();
        }

        function highlightViralTopic(headline, value) {
            if (!headline) return '<span style="color:rgba(255,255,255,0.35);">—</span>';

            const dim = (t) => `<span style="color:rgba(255,255,255,0.42);font-weight:400;">${t}</span>`;
            const bold = (t) => `<strong style="color:#e9d5ff;font-weight:700;">${t}</strong>`;

            if (!value) return dim(headline);

            const escaped = value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const regex = new RegExp(`(${escaped})`, 'i');
            const parts = headline.split(regex);

            if (parts.length === 1) {
                // valor não encontrado na frase — exibe headline apagada + value em destaque ao lado
                return dim(headline) + ' ' + bold(`[${value}]`);
            }

            return parts.map((part, i) =>
                regex.test(part) ? bold(part) : dim(part)
            ).join('');
        }

        function formatPlays(n) {
            if (!n) return '0';
            const num = parseInt(n);
            if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
            if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
            return num.toLocaleString('pt-BR');
        }

        function renderPvsItem(item, variableId, ii) {
            const added   = !!item.already_added;
            const key     = `${item.result_id}_${variableId}`;
            const checkId = `pvs-chk-${key}-${ii}`;

            const thumb = item.thumbnail
                ? `<img src="${item.thumbnail}" alt="thumb"
                       style="width:64px;height:64px;object-fit:cover;border-radius:6px;flex-shrink:0;${added ? 'opacity:0.4;' : ''}"
                       onerror="this.src='/back/static/placeholder.jpg'">`
                : `<div style="width:64px;height:64px;background:#1a1a2e;border-radius:6px;flex-shrink:0;display:flex;align-items:center;justify-content:center;${added ? 'opacity:0.4;' : ''}">
                       <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M7 4v16l13 -8z"/></svg>
                   </div>`;

            const rowStyle    = added ? 'border-bottom:1px solid rgba(255,255,255,0.04);opacity:0.55;' : 'border-bottom:1px solid rgba(255,255,255,0.05);';
            const valueStyle  = added ? 'font-size:0.93rem;color:rgba(255,255,255,0.35);text-decoration:line-through;' : 'font-size:0.93rem;color:#e9d5ff;';
            const checkboxHtml = added
                ? `<input type="checkbox" disabled checked style="width:16px;height:16px;flex-shrink:0;margin-top:4px;opacity:0.4;cursor:not-allowed;">`
                : `<input class="form-check-input pvs-checkbox flex-shrink-0 mt-1" type="checkbox"
                       id="${checkId}"
                       data-result-id="${item.result_id}"
                       data-variable-id="${variableId}"
                       data-content="${(item.value || '').replace(/"/g, '&quot;')}"
                       data-plays="${item.plays ?? ''}"
                       data-key="${key}-${ii}"
                       onchange="onPvsCheckboxChange(this)"
                       style="width:16px;height:16px;cursor:pointer;">`;
            const addedBadge = added
                ? `<span style="font-size:0.68rem;color:rgba(255,255,255,0.4);display:flex;align-items:center;gap:3px;">✓ Já adicionado</span>`
                : '';

            return `
                <div class="d-flex gap-3 align-items-start py-3" data-pvs-row="1" style="${rowStyle}">
                    ${checkboxHtml}
                    ${thumb}
                    <label ${added ? '' : `for="${checkId}"`} class="mb-0 flex-grow-1" style="${added ? 'cursor:default;' : 'cursor:pointer;'}line-height:1;">
                        <div class="pvs-item-title fw-bold mb-1" style="${valueStyle}">${item.value || '—'}</div>
                        <div class="mb-2" style="font-size:0.8rem;line-height:1.45;${added ? 'opacity:0.5;' : ''}">
                            ${highlightViralTopic(truncateHeadline(item.headline, item.value), item.value)}
                        </div>
                        <div class="pvs-item-meta d-flex align-items-center gap-2">
                            <span class="badge bg-purple-lt" style="font-size:0.68rem;${added ? 'opacity:0.5;' : ''}">
                                <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M7 4v16l13 -8z"/></svg>
                                ${formatPlays(item.plays)}
                            </span>
                            ${item.result_id
                                ? `<a href="/dashboard/user/library?viral_result_id=${item.result_id}" target="_blank"
                                    style="font-size:0.72rem;color:${added ? 'rgba(167,139,250,0.4)' : '#a78bfa'};text-decoration:none;"
                                    onmouseover="this.style.textDecoration='underline'"
                                    onmouseout="this.style.textDecoration='none'">Ver vídeo ↗</a>`
                                : ''}
                            ${addedBadge}
                        </div>
                    </label>
                </div>`;
        }

        // groups = [{ variable_id, variable_name, label, items: [{ result_id, plays, post_link, headline, value }] }]
        function renderPvsItems(groups) {
            const list = document.getElementById('pvs-list');
            list.innerHTML = '';

            groups.forEach((group, gi) => {
                const collapseId = `pvs-group-${gi}`;

                // Itens do grupo
                const itemsHtml = group.items.map((item, ii) => renderPvsItem(item, group.variable_id, ii)).join('');

                // Header do grupo (collapse)
                const li = document.createElement('li');
                li.className = 'list-group-item px-0 py-0';
                li.style.borderBottom = '1px solid rgba(255,255,255,0.08)';
                li.innerHTML = `
                    <div class="d-flex align-items-center gap-2 py-3">
                        <button class="d-flex align-items-center gap-2 flex-grow-1 p-0"
                                style="background:none;border:none;cursor:pointer;text-align:left;min-width:0;"
                                onclick="togglePvsCollapse('${collapseId}', this)">
                            <svg id="${collapseId}-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14"
                                viewBox="0 0 24 24" stroke-width="2.5" stroke="#a78bfa" fill="none"
                                style="transition:transform .2s;flex-shrink:0;transform:${gi === 0 ? 'rotate(180deg)' : 'rotate(0deg)'}">
                                <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                <path d="M6 9l6 6l6 -6"/>
                            </svg>
                            <span class="fw-semibold" style="font-size:0.88rem;color:#c4b5fd;">${group.label}</span>
                            <span class="badge bg-purple-lt ms-1" style="font-size:0.68rem;">${group.items.length}</span>
                        </button>
                        <div class="d-flex gap-1 flex-shrink-0">
                            <button onclick="sortPvsGroup(${gi}, 'plays', this)"
                                id="${collapseId}-sort-plays"
                                style="font-size:0.68rem;padding:2px 8px;border-radius:10px;border:1px solid rgba(109,40,217,0.3);background:rgba(109,40,217,0.18);color:#a78bfa;cursor:pointer;font-weight:600;transition:all .15s;">
                                ↓ Views
                            </button>
                            <button onclick="sortPvsGroup(${gi}, 'recent', this)"
                                id="${collapseId}-sort-recent"
                                style="font-size:0.68rem;padding:2px 8px;border-radius:10px;border:1px solid rgba(255,255,255,0.1);background:transparent;color:rgba(255,255,255,0.4);cursor:pointer;font-weight:600;transition:all .15s;">
                                Mais recente
                            </button>
                        </div>
                    </div>
                    <div id="${collapseId}" style="display:${gi === 0 ? 'block' : 'none'};padding-bottom:4px;">
                        <div id="${collapseId}-items">${itemsHtml}</div>
                    </div>`;

                list.appendChild(li);
            });
        }

        function selectAllPvsItems(btn) {
            const checkboxes = Array.from(
                document.querySelectorAll('#pvs-list .pvs-checkbox:not(:disabled)')
            );
            const allChecked = checkboxes.every(c => c.checked);
            checkboxes.forEach(c => {
                c.checked = !allChecked;
                onPvsCheckboxChange(c);
            });
            const label = document.getElementById('pvs-select-all-label');
            label.textContent = allChecked ? 'Selecionar todos' : 'Desmarcar todos';
        }

        function sortPvsGroup(gi, sortType, clickedBtn) {
            const group      = _pvsItems[gi];
            const collapseId = `pvs-group-${gi}`;
            const container  = document.getElementById(`${collapseId}-items`);
            if (!container || !group) return;

            // Atualiza visual dos botões
            const playsBtn  = document.getElementById(`${collapseId}-sort-plays`);
            const recentBtn = document.getElementById(`${collapseId}-sort-recent`);
            const activeStyle   = 'font-size:0.68rem;padding:2px 8px;border-radius:10px;border:1px solid rgba(109,40,217,0.3);background:rgba(109,40,217,0.18);color:#a78bfa;cursor:pointer;font-weight:600;transition:all .15s;';
            const inactiveStyle = 'font-size:0.68rem;padding:2px 8px;border-radius:10px;border:1px solid rgba(255,255,255,0.1);background:transparent;color:rgba(255,255,255,0.4);cursor:pointer;font-weight:600;transition:all .15s;';
            playsBtn.style.cssText  = sortType === 'plays'  ? activeStyle : inactiveStyle;
            recentBtn.style.cssText = sortType === 'recent' ? activeStyle : inactiveStyle;

            // Ordena uma cópia dos itens
            const sorted = [...group.items].sort((a, b) => {
                if (sortType === 'plays') {
                    return (parseInt(b.plays) || 0) - (parseInt(a.plays) || 0);
                }
                return (b.result_id || 0) - (a.result_id || 0);
            });

            container.innerHTML = sorted.map((item, ii) => renderPvsItem(item, group.variable_id, ii)).join('');
        }

        function togglePvsCollapse(id, btn) {
            const el   = document.getElementById(id);
            const icon = document.getElementById(id + '-icon');
            const open = el.style.display === 'none';
            el.style.display     = open ? 'block' : 'none';
            icon.style.transform = open ? 'rotate(180deg)' : '';
        }

        function onPvsCheckboxChange(el) {
            const key = el.dataset.key;
            if (el.checked) {
                _pvsSelectedKeys.add(key);
            } else {
                _pvsSelectedKeys.delete(key);
            }
            const count = _pvsSelectedKeys.size;
            document.getElementById('pvs-selected-count').textContent = count;
            document.getElementById('pvs-save-btn').style.display = count > 0 ? 'inline-flex' : 'none';
        }

        async function saveSelectedPvsVariables() {
            if (_pvsSelectedKeys.size === 0) return;

            const checkboxes = document.querySelectorAll('.pvs-checkbox:checked');
            const items = Array.from(checkboxes).map(el => ({
                variable_id:           parseInt(el.dataset.variableId),
                content:               el.dataset.content,
                eng_reversa_result_id: parseInt(el.dataset.resultId),
                plays:                 el.dataset.plays || null,
            }));

            const btn = document.getElementById('pvs-save-btn');
            btn.disabled = true;
            const originalHtml = btn.innerHTML;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span> Salvando...';

            let fetchOk = false;
            try {
                const res  = await fetch('/dashboard/user/searches/profile-viral-search/save', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    },
                    body: JSON.stringify({ items })
                });
                const data = await res.json();
                fetchOk = true;

                if (data.success) {
                    toastr.success(data.message);
                    _pvsSelectedKeys.clear();
                    document.getElementById('pvs-selected-count').textContent = '0';
                    btn.style.display = 'none';
                    document.getElementById('pvs-select-all-label').textContent = 'Selecionar todos';

                    // Aplicar visual "já adicionado" — erros de DOM não disparam toast
                    checkboxes.forEach(el => {
                        try {
                            const row = el.closest('[data-pvs-row]');
                            el.checked  = false;
                            el.disabled = true;
                            el.style.cssText += ';opacity:0.4;cursor:not-allowed;';
                            if (!row) return;
                            row.style.opacity = '0.55';
                            const title = row.querySelector('.pvs-item-title');
                            if (title) {
                                title.style.textDecoration = 'line-through';
                                title.style.color = 'rgba(255,255,255,0.35)';
                            }
                            const meta = row.querySelector('.pvs-item-meta');
                            if (meta && !meta.querySelector('.pvs-added-badge')) {
                                const badge = document.createElement('span');
                                badge.className = 'pvs-added-badge';
                                badge.style.cssText = 'font-size:0.68rem;color:rgba(255,255,255,0.4);display:flex;align-items:center;gap:3px;';
                                badge.textContent = '✓ Já adicionado';
                                meta.appendChild(badge);
                            }
                        } catch (_) {}
                    });
                } else {
                    toastr.error(data.message || 'Erro ao salvar.');
                }
            } catch (e) {
                if (!fetchOk) toastr.error('Erro ao processar a solicitação.');
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalHtml;
            }
        }
    