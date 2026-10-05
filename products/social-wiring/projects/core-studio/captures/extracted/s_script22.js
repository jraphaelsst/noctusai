
        // ─── Unified View (Minha Pesquisa) ───────────────────────────────────────

        window.unifiedAllItems = [];
        window.unifiedFilteredItems = [];
        window._unifiedLoading = false;
        window.unifiedVariableLabels = {"18":"Desejos do meu p\u00fablico","17":"Dores do meu p\u00fablico ","16":"Caracter\u00edsticas demogr\u00e1ficas do meu p\u00fablico","25":"Qualidades do meu p\u00fablico","26":"Defeitos do meu p\u00fablico","15":"Itens conhecidos pelo meu p\u00fablico","14":"Institui\u00e7\u00f5es conhecidas pelo meu p\u00fablico","13":"Pessoas e personagens conhecidos pelo meu p\u00fablico","32":"Inimigos do meu p\u00fablico ","11":"Filmes, s\u00e9ries ou m\u00fasicas conhecidas pelo meu p\u00fablico","19":"Eventos conhecidos pelo meu p\u00fablico ","20":"Locais conhecidos pelo meu p\u00fablico","21":"Momentos de vida do meu p\u00fablico","10":"Obje\u00e7\u00f5es do meu p\u00fablico ","9":"Medos do meu p\u00fablico","8":"Cren\u00e7as do meu p\u00fablico ","5":"Desejos e conquistas que eu realizei ","34":"Produtos conhecidos pelo meu p\u00fablico","4":"Situa\u00e7\u00f5es dolorosas que eu enfrentei ","30":"Meus h\u00e1bitos e hobbies ","31":"Minha forma\u00e7\u00e3o profissional ","28":"Quem eu sou (idade, estado civil, nacionalidade, etc)","7":"Minhas qualidades","27":"Meus defeitos","6":"T\u00e9cnicas, servi\u00e7os e procedimentos que eu efetuo ","12":"T\u00e9cnicas, servi\u00e7os e procedimentos que eu n\u00e3o recomendo","3":"H\u00e1bitos que eu recomendo para o meu p\u00fablico","2":"H\u00e1bitos que eu n\u00e3o recomendo para o meu p\u00fablico ","1":"Cren\u00e7as e ideias que eu defendo","22":"Verbos Poderosos","23":"Adjetivos Poderosos","24":"Momento do dia","29":"GPT"};
        window.unifiedVariableTypes = {"18":"avatar","17":"avatar","16":"avatar","25":"avatar","26":"avatar","15":"avatar","14":"avatar","13":"avatar","32":"avatar","11":"avatar","19":"avatar","20":"avatar","21":"avatar","10":"avatar","9":"avatar","8":"avatar","5":"especialista","34":"avatar","4":"especialista","30":"especialista","31":"especialista","28":"especialista","7":"especialista","27":"especialista","6":"especialista","12":"especialista","3":"especialista","2":"especialista","1":"especialista","22":null,"23":null,"24":null,"29":null};

        window.unifiedState = {
            sort: 'recent',
            variableId: '',
            statusFilter: 'approved',
            groupBy: false,
            rendered: 0,
            PAGE_SIZE: 20
        };

        async function loadUnifiedData() {
            if (window._unifiedLoading) return;
            window._unifiedLoading = true;

            const container = document.getElementById('unified-items-container');
            const emptyState = document.getElementById('unified-empty-state');

            if (container) {
                container.innerHTML = `
                    <div class="text-center py-5">
                        <div class="spinner-border text-primary" role="status" style="width:2rem;height:2rem;"></div>
                        <p class="text-muted mt-2">Carregando itens...</p>
                    </div>
                `;
            }
            if (emptyState) emptyState.style.display = 'none';

            try {
                const [r1, r2] = await Promise.all([
                    fetch('/dashboard/user/searches/variables/items?type=especialista'),
                    fetch('/dashboard/user/searches/variables/items?type=avatar')
                ]);
                const [d1, d2] = await Promise.all([r1.json(), r2.json()]);

                window.unifiedAllItems = [];

                function processUnifiedData(result, variableType) {
                    if (!result.success) return;
                    Object.keys(result.data).forEach(varId => {
                        const varData = result.data[varId];
                        const varLabel = window.unifiedVariableLabels[varId] || varId;

                        (varData.approved_manual || []).forEach(item => {
                            window.unifiedAllItems.push({
                                ...item, variableId: varId, variableLabel: varLabel,
                                variableType, status: 'approved_manual'
                            });
                        });
                        (varData.approved || []).forEach(item => {
                            window.unifiedAllItems.push({
                                ...item, variableId: varId, variableLabel: varLabel,
                                variableType, status: 'approved'
                            });
                        });
                        (varData.pending || []).forEach(item => {
                            window.unifiedAllItems.push({
                                ...item, variableId: varId, variableLabel: varLabel,
                                variableType, status: 'pending'
                            });
                        });
                    });
                }

                processUnifiedData(d1, 'especialista');
                processUnifiedData(d2, 'avatar');

                window.unifiedState.rendered = 0;
                applyUnifiedFilters();

            } catch (error) {
                console.error('Erro ao carregar dados unificados:', error);
                if (container) {
                    container.innerHTML = `
                        <div class="alert alert-danger" style="max-width:600px">
                            <h4 class="alert-title">Erro ao carregar</h4>
                            <div>${error.message}</div>
                            <button class="btn btn-primary mt-3" onclick="window._unifiedLoading=false;loadUnifiedData()">Tentar novamente</button>
                        </div>
                    `;
                }
            } finally {
                window._unifiedLoading = false;
            }
        }

        function applyUnifiedFilters() {
            let items = [...window.unifiedAllItems];

            if (window.unifiedState.variableId) {
                items = items.filter(i => String(i.variableId) === String(window.unifiedState.variableId));
            }

            if (window.unifiedState.statusFilter === 'approved') {
                items = items.filter(i => i.status !== 'pending');
            } else if (window.unifiedState.statusFilter === 'pending') {
                items = items.filter(i => i.status === 'pending');
            }

            if (window.unifiedState.sort === 'plays') {
                items.sort((a, b) => (b.plays || 0) - (a.plays || 0));
            } else {
                items.sort((a, b) => b.id - a.id);
            }

            window.unifiedFilteredItems = items;
            window.unifiedState.rendered = 0;

            const container = document.getElementById('unified-items-container');
            if (container) container.innerHTML = '';

            const emptyState = document.getElementById('unified-empty-state');
            if (emptyState) emptyState.style.display = items.length === 0 ? 'block' : 'none';

            const totalCount = document.getElementById('unified-total-count');
            if (totalCount) totalCount.textContent = items.length > 0 ? `${items.length} item(s)` : '';

            if (window.unifiedState.groupBy) {
                renderUnifiedGrouped();
            } else {
                renderNextUnifiedPage();
            }
        }

        function renderNextUnifiedPage() {
            const items = window.unifiedFilteredItems || [];
            const { rendered, PAGE_SIZE } = window.unifiedState;
            if (rendered >= items.length) return;

            const container = document.getElementById('unified-items-container');
            if (!container) return;

            const slice = items.slice(rendered, rendered + PAGE_SIZE);
            const offset = window.unifiedState.rendered;
            const html = slice.map((item, i) => renderUnifiedItem(item, offset + i)).join('');
            container.insertAdjacentHTML('beforeend', html);
            window.unifiedState.rendered += slice.length;
        }

        function renderUnifiedGrouped() {
            const items = window.unifiedFilteredItems || [];
            const container = document.getElementById('unified-items-container');
            if (!container) return;
            container.innerHTML = '';

            const groups = {};
            items.forEach(item => {
                const key = item.variableId;
                if (!groups[key]) groups[key] = { label: item.variableLabel, type: item.variableType, items: [] };
                groups[key].items.push(item);
            });

            Object.values(groups).forEach(group => {
                const typeLabel = group.type === 'especialista' ? 'Sobre Mim' : 'Meu Público';
                const typeBg = group.type === 'especialista' ? '7c3aed' : '0d6efd';
                const groupHtml = `
                    <div class="mb-4">
                        <div class="d-flex align-items-center gap-2 mb-2 pb-2" style="border-bottom:1px solid #E1C8FF26">
                            <span style="font-weight:600;color:#E1C8FF;font-size:0.95rem">${group.label}</span>
                            <span class="badge text-white" style="background:#${typeBg};font-size:0.7rem">${typeLabel}</span>
                            <span class="badge" style="background:#9945FF33;color:#c084fc;border:1px solid #9945FF44;font-size:0.7rem">${group.items.length} item(s)</span>
                        </div>
                        <div>${group.items.map((item, i) => renderUnifiedItem(item, i)).join('')}</div>
                    </div>
                `;
                container.insertAdjacentHTML('beforeend', groupHtml);
            });

            window.unifiedState.rendered = items.length;
        }

        function renderUnifiedItem(item, index = 0) {
            const isApproved = item.status !== 'pending';
            const isManual = item.status === 'approved_manual';
            const varTypeLabel = item.variableType === 'especialista' ? 'Sobre Mim' : 'Meu Público';
            const source = isManual ? 'content' : 'pending';
            const escapedContent = (item.content || '').replace(/'/g, "\\'");

            const accentColor = isApproved ? '#9945FF' : '#f97316';
            const metaParts = [item.variableLabel, varTypeLabel];
            if (isManual) metaParts.push('manual');
            if (item.plays) metaParts.push(formatNumber(item.plays) + ' views');
            const metaText = metaParts.join(' · ');

            const btnStyle = 'background:none;border:none;cursor:pointer;padding:4px;opacity:0.35;transition:opacity .15s;color:#fff;display:flex;align-items:center;';

            let actionBtns = '';
            if (!isApproved) {
                actionBtns = `
                    <button type="button" style="${btnStyle}" onmouseover="this.style.opacity='.9'" onmouseout="this.style.opacity='.35'" onclick="openUserVariableModal(${item.eng_reversa_result_id || 0}, '${escapedContent}')" title="Ver na biblioteca">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"></path><circle cx="12" cy="12" r="3"></circle></svg>
                    </button>
                    <button type="button" style="${btnStyle}" onmouseover="this.style.opacity='.9'" onmouseout="this.style.opacity='.35'" onclick="setAttributeApprove(${item.id})" data-bs-toggle="modal" data-bs-target="#modal-approved-variable" title="Aprovar">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path d="M18 6 7 17l-5-5"/><path d="m22 10-7.5 7.5L13 16"/></svg>
                    </button>
                    <button type="button" style="${btnStyle}" onmouseover="this.style.opacity='.9'" onmouseout="this.style.opacity='.35'" onclick="setAttributeReject(${item.id})" data-bs-toggle="modal" data-bs-target="#modal-rejected-variable" title="Rejeitar">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M18 6l-12 12"/><path d="M6 6l12 12"/></svg>
                    </button>
                `;
            } else {
                const viewBtn = !isManual ? `
                    <button type="button" style="${btnStyle}" onmouseover="this.style.opacity='.9'" onmouseout="this.style.opacity='.35'" onclick="openUserVariableModal(${item.eng_reversa_result_id || 0}, '${escapedContent}')" title="Ver na biblioteca">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"></path><circle cx="12" cy="12" r="3"></circle></svg>
                    </button>` : '';
                actionBtns = viewBtn + `
                    <button type="button" style="${btnStyle}" onmouseover="this.style.opacity='.9'" onmouseout="this.style.opacity='.35'" onclick="openUnifiedRemoveModal(${item.id}, '${item.variableId}', '${source}')" title="Excluir">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 7l16 0"/><path d="M10 11l0 6"/><path d="M14 11l0 6"/><path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12"/><path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3"/></svg>
                    </button>
                `;
            }

            return `
                <div class="pending-item-container unified-item" data-item-id="${item.id}" data-variable-id="${item.variableId}" data-status="${item.status}"
                    style="border-bottom:1px solid #ffffff0f;background:${index % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.025)'}">
                    <div data-item-id="${item.id}" data-source="${source}"
                        style="padding:10px 4px 10px 8px;display:flex;align-items:center;gap:12px">
                        <div style="width:3px;height:36px;border-radius:2px;flex-shrink:0;background:${accentColor};opacity:0.7"></div>
                        <div class="form-check mb-0 flex-shrink-0">
                            <input class="form-check-input item-checkbox-unified" type="checkbox"
                                value="${item.id}" data-item-id="${item.id}"
                                data-variable-id="${item.variableId}" data-status="${item.status}"
                                data-source="${source}" onchange="updateUnifiedBulkBar()">
                        </div>
                        <div style="flex:1;min-width:0">
                            <div style="font-size:0.88rem;font-weight:500;color:#e8e0ff;line-height:1.35;word-break:break-word">${item.content}</div>
                            <div style="font-size:0.68rem;color:#ffffff40;margin-top:2px">${metaText}</div>
                        </div>
                        <div style="display:flex;align-items:center;flex-shrink:0">
                            ${actionBtns}
                        </div>
                    </div>
                </div>
            `;
        }

        function setUnifiedSort(sort) {
            window.unifiedState.sort = sort;
            const isRecent = sort === 'recent';
            const activeStyle = 'linear-gradient(135deg,#7c3aed,#9945FF)';
            const recentBtn = document.getElementById('unified-sort-recent');
            const playsBtn = document.getElementById('unified-sort-plays');
            if (recentBtn) {
                recentBtn.style.background = isRecent ? activeStyle : 'transparent';
                recentBtn.style.color = isRecent ? '#fff' : '#ffffff60';
            }
            if (playsBtn) {
                playsBtn.style.background = isRecent ? 'transparent' : activeStyle;
                playsBtn.style.color = isRecent ? '#ffffff60' : '#fff';
            }
            applyUnifiedFilters();
        }

        function setUnifiedStatus(status) {
            window.unifiedState.statusFilter = status;
            ['approved', 'pending'].forEach(s => {
                const btn = document.getElementById(`unified-filter-${s}`);
                if (!btn) return;
                const isActive = s === status;
                const activeBg = s === 'pending' ? 'linear-gradient(135deg,#c2410c,#f97316)' : 'linear-gradient(135deg,#7c3aed,#9945FF)';
                btn.style.background = isActive ? activeBg : 'transparent';
                btn.style.color = isActive ? '#fff' : '#ffffff60';
            });
            applyUnifiedFilters();
        }

        function setUnifiedVariableFilter(variableId) {
            window.unifiedState.variableId = variableId;
            applyUnifiedFilters();
        }

        function toggleUnifiedGroupBy(btn) {
            window.unifiedState.groupBy = !window.unifiedState.groupBy;
            const active = window.unifiedState.groupBy;
            btn.style.background = active ? 'linear-gradient(135deg,#7c3aed,#9945FF)' : 'transparent';
            btn.style.color = active ? '#fff' : '#ffffff60';
            applyUnifiedFilters();
        }

        function updateUnifiedBulkBar() {
            const checked = document.querySelectorAll('#unified-items-container .item-checkbox-unified:checked');
            const bulkBar = document.getElementById('unified-bulk-bar');
            const countEl = document.getElementById('unified-bulk-count');
            const modalCountEl = document.getElementById('bulk-actions-count');
            const approveBtn = document.getElementById('bulk-action-approve-btn');
            if (bulkBar) bulkBar.style.display = checked.length > 0 ? 'flex' : 'none';
            if (countEl) countEl.textContent = checked.length;
            if (modalCountEl) modalCountEl.textContent = checked.length;
            if (approveBtn) approveBtn.style.display = window.unifiedState.statusFilter === 'pending' ? 'inline-flex' : 'none';
        }

        window._addItemPromptActive = false;

        async function openAddItemModal(variableId, variableLabel) {
            const filterVar = document.getElementById('unified-variable-filter');
            const hiddenId = document.getElementById('add-item-variable-id');
            const labelEl = document.getElementById('add-item-variable-label');

            const resolvedId = variableId || (filterVar && filterVar.value) || '';
            const resolvedLabel = variableLabel
                || (filterVar && filterVar.value && filterVar.options[filterVar.selectedIndex]?.text)
                || '';

            if (hiddenId) hiddenId.value = resolvedId;
            if (labelEl) labelEl.textContent = resolvedLabel && resolvedLabel !== 'Todas as variáveis' ? resolvedLabel : '';

            const ta = document.getElementById('add-item-value');
            ta.value = '';
            const countEl = document.getElementById('add-item-line-count');
            if (countEl) countEl.textContent = '0 itens';
            ta.oninput = () => {
                const lines = ta.value.split('\n').filter(l => l.trim()).length;
                if (countEl) countEl.textContent = lines === 0 ? '0 itens' : `${lines} ${lines === 1 ? 'item' : 'itens'}`;
            };

            // reset modal state
            resetAddItemModal();
            switchAddTab('items', document.querySelector('#modal-add-item .add-tab-btn'));

            // load prompt config
            try {
                const res = await fetch('/dashboard/user/searches/add-item-prompt');
                const data = await res.json();
                window._addItemPromptActive = data.is_active && !!data.prompt_system;
                const promptTa = document.getElementById('add-prompt-system');
                if (promptTa) promptTa.value = data.prompt_system || '';
                const inclVars = document.getElementById('add-prompt-include-variables');
                if (inclVars) inclVars.checked = !!data.include_variables;
                const statusEl = document.getElementById('add-item-process-status');
                if (statusEl) statusEl.style.display = window._addItemPromptActive ? 'inline' : 'none';
            } catch(e) {}

            new bootstrap.Modal(document.getElementById('modal-add-item')).show();
            setTimeout(() => ta.focus(), 300);
        }

        function _addModalSetProcessing(show) {
            const ids = ['add-modal-tabs-row','add-tab-items','add-tab-prompt','add-modal-footer'];
            ids.forEach(id => { const el = document.getElementById(id); if (el) el.style.display = show ? 'none' : ''; });
            const proc = document.getElementById('add-item-state-processing');
            const res = document.getElementById('add-item-state-result');
            const resFooter = document.getElementById('add-result-footer');
            if (proc) proc.style.display = show ? 'block' : 'none';
            if (res) res.style.display = 'none';
            if (resFooter) resFooter.style.display = 'none';
            // restore tabs to default visible state when hiding
            if (!show) {
                const tabsRow = document.getElementById('add-modal-tabs-row');
                if (tabsRow) tabsRow.style.display = '';
                const itemsTab = document.getElementById('add-tab-items');
                if (itemsTab) itemsTab.style.display = 'block';
                const footer = document.getElementById('add-modal-footer');
                if (footer) footer.style.display = '';
            }
        }

        function _addModalShowResult(jobResult) {
            document.getElementById('add-item-state-processing').style.display = 'none';
            const res = document.getElementById('add-item-state-result');
            const resFooter = document.getElementById('add-result-footer');
            const container = document.getElementById('add-result-items');
            container.innerHTML = '';

            const chevron = `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M6 9l6 6l6 -6"/></svg>`;

            if (jobResult.status === 'error') {
                container.innerHTML = `
                    <div class="add-result-banner error">
                        <div class="arb-icon">
                            <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 9v4"/><path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636 -2.87l-8.106 -13.536a1.914 1.914 0 0 0 -3.274 0z"/><path d="M12 16h.01"/></svg>
                        </div>
                        <div>
                            <div class="arb-count" style="font-size:.85rem">Erro ao processar</div>
                            <div class="arb-label" style="color:#f87171aa">${jobResult.message || 'Ocorreu um erro inesperado.'}</div>
                        </div>
                    </div>`;
            } else {
                const saved = jobResult.saved || 0;
                const classified = jobResult.classified || {};
                const unclassified = jobResult.unclassified || [];

                // Banner principal
                container.innerHTML += `
                    <div class="add-result-banner success">
                        <div class="arb-icon">
                            <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M5 12l5 5l10 -10"/></svg>
                        </div>
                        <div>
                            <div class="arb-count">${saved}</div>
                            <div class="arb-label">${saved === 1 ? 'item adicionado' : 'itens adicionados'} com sucesso</div>
                        </div>
                    </div>`;

                // Acordeão "Ver detalhes"
                const hasDetails = Object.keys(classified).length > 0 || unclassified.length > 0;
                if (hasDetails) {
                    let detailsHtml = '';

                    // Itens classificados por variável
                    for (const [label, items] of Object.entries(classified)) {
                        const itemsHtml = items.map(c => `<div class="add-details-item">${c}</div>`).join('');
                        detailsHtml += `
                            <div class="add-details-group">
                                <div class="add-details-group-label">${label}</div>
                                ${itemsHtml}
                            </div>`;
                    }

                    // Não classificados
                    if (unclassified.length > 0) {
                        const unItems = unclassified.map(u => `<div class="add-details-item">${u.content} <span style="font-size:.65rem;opacity:.5;font-family:monospace">${u.token}</span></div>`).join('');
                        detailsHtml += `
                            <div class="add-details-group warn">
                                <div class="add-details-group-label">Não classificados (${unclassified.length})</div>
                                ${unItems}
                            </div>`;
                    }

                    container.innerHTML += `
                        <button type="button" class="add-details-toggle" onclick="this.classList.toggle('open');this.nextElementSibling.style.display=this.classList.contains('open')?'block':'none'">
                            <span>Ver detalhes</span>
                            ${chevron}
                        </button>
                        <div class="add-details-body">${detailsHtml}</div>`;
                }
            }

            res.style.display = 'block';
            resFooter.style.display = '';

            if (jobResult.status !== 'error' && (jobResult.saved || 0) > 0) {
                window._unifiedLoading = false;
                loadUnifiedData();
            }
        }

        function resetAddItemModal() {
            document.getElementById('add-item-state-processing').style.display = 'none';
            document.getElementById('add-item-state-result').style.display = 'none';
            document.getElementById('add-result-footer').style.display = 'none';
            document.getElementById('add-modal-tabs-row').style.display = '';
            document.getElementById('add-tab-items').style.display = 'block';
            const promptTab = document.getElementById('add-tab-prompt');
            if (promptTab) promptTab.style.display = 'none';
            document.getElementById('add-modal-footer').style.display = '';
            document.querySelectorAll('#modal-add-item .add-tab-btn').forEach((b,i) => b.classList.toggle('active', i===0));
            document.getElementById('add-item-value').value = '';
            document.getElementById('add-item-line-count').textContent = '0 itens';
        }

        async function submitAddItem() {
            const variableId = document.getElementById('add-item-variable-id').value;
            const raw = document.getElementById('add-item-value').value;
            const lines = raw.split('\n').map(l => l.trim()).filter(l => l.length > 0);
            if (!lines.length) { toastr.warning('Digite ao menos um item.'); return; }

            const csrf = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

            if (window._addItemPromptActive) {
                _addModalSetProcessing(true);
                document.getElementById('add-processing-label').textContent = 'Classificando itens com IA...';
                document.getElementById('add-processing-sub').textContent = 'Aguarde, isso pode levar alguns instantes';

                const syncTimeout = 90000; // 90s
                const abortCtrl = new AbortController();
                const abortTimer = setTimeout(() => abortCtrl.abort(), syncTimeout);

                try {
                    const syncRes = await fetch('/dashboard/user/searches/add-items-sync', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': csrf },
                        body: JSON.stringify({ text: lines.join('\n') }),
                        signal: abortCtrl.signal,
                    });
                    clearTimeout(abortTimer);
                    const syncData = await syncRes.json();
                    _addModalShowResult(syncData);
                    return;
                } catch (e) {
                    clearTimeout(abortTimer);
                    // timeout ou erro de rede → fallback para job assíncrono
                    document.getElementById('add-processing-label').textContent = 'Processando em segundo plano...';
                    document.getElementById('add-processing-sub').textContent = 'A resposta demorou mais que o esperado, avisaremos quando terminar';
                }

                // fallback: job com polling
                try {
                    const dispatchRes = await fetch('/dashboard/user/searches/add-items-job', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': csrf },
                        body: JSON.stringify({ text: lines.join('\n') })
                    });
                    const dispatchData = await dispatchRes.json();
                    if (!dispatchData.success) {
                        _addModalShowResult({ status: 'error', message: dispatchData.message || 'Erro ao iniciar processamento.' });
                        return;
                    }

                    const jobId = dispatchData.job_id;
                    const maxAttempts = 300;
                    let attempts = 0;

                    const poll = async () => {
                        if (attempts++ >= maxAttempts) {
                            _addModalShowResult({ status: 'error', message: 'Tempo limite atingido. Tente novamente.' });
                            return;
                        }
                        try {
                            const statusRes = await fetch(`/dashboard/user/searches/add-items-job/${jobId}`);
                            const status = await statusRes.json();
                            if (status.status === 'processing' || status.status === 'pending') {
                                setTimeout(poll, 2000);
                                return;
                            }
                            _addModalShowResult(status);
                        } catch(e) {
                            setTimeout(poll, 2000);
                        }
                    };
                    setTimeout(poll, 2000);
                } catch (e) {
                    _addModalShowResult({ status: 'error', message: 'Erro de conexão. Tente novamente.' });
                }
                return;
            }

            // Prompt inativo: salva diretamente linha a linha
            const btn = document.getElementById('add-item-submit-btn');
            const btnLabel = `<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 5l0 14"/><path d="M5 12l14 0"/></svg> Salvar itens`;
            try {
                let saved = 0;
                for (let i = 0; i < lines.length; i++) {
                    if (btn) { btn.classList.add('loading'); btn.textContent = `Salvando ${i+1}/${lines.length}...`; }
                    const res = await fetch('/dashboard/user/searches/variables/contents/add', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': csrf },
                        body: JSON.stringify({ id: variableId, value: lines[i] })
                    });
                    const data = await res.json();
                    if (data.type === 'success') saved++;
                }
                if (saved > 0) {
                    toastr.success(`${saved} ${saved === 1 ? 'item adicionado' : 'itens adicionados'} com sucesso!`);
                    bootstrap.Modal.getInstance(document.getElementById('modal-add-item')).hide();
                    window._unifiedLoading = false;
                    await loadUnifiedData();
                } else {
                    toastr.error('Nenhum item foi salvo.');
                }
            } catch (e) {
                toastr.error('Erro ao salvar itens.');
            } finally {
                if (btn) { btn.classList.remove('loading'); btn.innerHTML = btnLabel; }
            }
        }

        function switchAddTab(tab, btn) {
            document.getElementById('add-tab-items').style.display = tab === 'items' ? 'block' : 'none';
            const promptTab = document.getElementById('add-tab-prompt');
            if (promptTab) promptTab.style.display = tab === 'prompt' ? 'block' : 'none';
            document.querySelectorAll('#modal-add-item .add-tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const submitBtn = document.getElementById('add-item-submit-btn');
            const testBtn = document.getElementById('add-prompt-test-btn');
            const savePromptBtn = document.getElementById('add-prompt-save-btn');
            if (submitBtn) submitBtn.style.display = tab === 'items' ? 'inline-flex' : 'none';
            if (testBtn) testBtn.style.display = tab === 'prompt' ? 'inline-flex' : 'none';
            if (savePromptBtn) savePromptBtn.style.display = tab === 'prompt' ? 'inline-flex' : 'none';
        }

        async function saveAddPrompt() {
            const prompt = document.getElementById('add-prompt-system')?.value?.trim();
            const btn = document.getElementById('add-prompt-save-btn');
            if (btn) { btn.classList.add('loading'); btn.textContent = 'Salvando...'; }
            try {
                const res = await fetch('/dashboard/user/searches/add-item-prompt', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content') },
                    body: JSON.stringify({
                        prompt_system: prompt || ' ',
                        is_active: !!prompt,
                        include_variables: document.getElementById('add-prompt-include-variables')?.checked ?? false
                    })
                });
                const data = await res.json();
                if (data.success) {
                    toastr.success('Prompt salvo!');
                    window._addItemPromptActive = !!prompt;
                    const statusEl = document.getElementById('add-item-process-status');
                    if (statusEl) statusEl.style.display = window._addItemPromptActive ? 'inline' : 'none';
                } else {
                    toastr.error(data.message || 'Erro ao salvar prompt.');
                }
            } catch(e) { toastr.error('Erro ao salvar prompt.'); }
            finally { if (btn) { btn.classList.remove('loading'); btn.textContent = 'Salvar prompt'; } }
        }

        async function testAddPrompt() {
            const prompt = document.getElementById('add-prompt-system')?.value?.trim();
            const text = document.getElementById('add-prompt-test-input')?.value?.trim();
            if (!prompt) { toastr.warning('Digite o prompt system primeiro.'); return; }
            if (!text) { toastr.warning('Digite um texto para testar.'); return; }
            const btn = document.getElementById('add-prompt-test-btn');
            const resultBox = document.getElementById('add-prompt-result');
            if (btn) { btn.classList.add('loading'); btn.innerHTML = '⏳ Testando...'; }
            if (resultBox) { resultBox.style.display = 'none'; resultBox.textContent = ''; }
            try {
                const res = await fetch('/dashboard/user/searches/add-item-prompt/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content') },
                    body: JSON.stringify({
                        prompt_system: prompt,
                        text,
                        include_variables: document.getElementById('add-prompt-include-variables')?.checked ?? false
                    })
                });
                const data = await res.json();
                if (data.success && resultBox) {
                    resultBox.textContent = data.result;
                    resultBox.style.display = 'block';
                } else { toastr.error(data.message || 'Erro no teste.'); }
            } catch(e) { toastr.error('Erro ao testar prompt.'); }
            finally { if (btn) { btn.classList.remove('loading'); btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M7 4v16l13 -8z"/></svg> Testar prompt'; } }
        }

        function openBulkActionsModal() {
            updateUnifiedBulkBar();
            new bootstrap.Modal(document.getElementById('modal-bulk-actions')).show();
        }

        function toggleSelectAllUnified() {
            const checkboxes = document.querySelectorAll('#unified-items-container .item-checkbox-unified');
            const allChecked = Array.from(checkboxes).every(cb => cb.checked);
            checkboxes.forEach(cb => { cb.checked = !allChecked; });
            const label = document.getElementById('unified-select-all-label');
            if (label) label.textContent = allChecked ? 'Selecionar todos' : 'Desmarcar todos';
            updateUnifiedBulkBar();
        }

        async function bulkApproveUnified() {
            const checked = document.querySelectorAll('#unified-items-container .item-checkbox-unified:checked');
            const pendingIds = Array.from(checked)
                .filter(cb => cb.dataset.status === 'pending')
                .map(cb => cb.dataset.itemId);

            if (pendingIds.length === 0) {
                toastr.info('Nenhum item pendente selecionado para aprovação.');
                return;
            }

            let successCount = 0;
            for (const id of pendingIds) {
                try {
                    const res = await fetch(`/dashboard/user/searches/approve-pending-item/${id}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                        }
                    });
                    const data = await res.json();
                    if (data.success || data.type === 'success') successCount++;
                } catch (e) { console.error(e); }
            }

            if (successCount > 0) {
                toastr.success(`${successCount} item(s) aprovado(s) com sucesso!`);
                window._unifiedLoading = false;
                await loadUnifiedData();
            }
        }

        async function bulkDeleteUnified() {
            const checked = document.querySelectorAll('#unified-items-container .item-checkbox-unified:checked');
            if (checked.length === 0) return;

            window._pendingBulkDeleteItems = Array.from(checked).map(cb => ({
                id: cb.dataset.itemId, variableId: cb.dataset.variableId, source: cb.dataset.source
            }));

            const msgEl = document.getElementById('bulk-delete-message');
            if (msgEl) msgEl.textContent = `Você realmente deseja excluir ${checked.length} item(s) selecionado(s)?`;

            new bootstrap.Modal(document.getElementById('modal-confirm-bulk-delete')).show();
        }

        async function executeBulkDeleteUnified() {
            const items = window._pendingBulkDeleteItems || [];
            if (items.length === 0) return;

            const modalEl = document.getElementById('modal-confirm-bulk-delete');
            const m = bootstrap.Modal.getInstance(modalEl);
            if (m) m.hide();

            let successCount = 0;
            for (const item of items) {
                try {
                    const res = await fetch('dashboard/user/searches/variables/contents/remove', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                        },
                        body: JSON.stringify({ id: item.id, source: item.source || 'content' })
                    });
                    const data = await res.json();
                    if (data.success || data.type === 'success') successCount++;
                } catch (e) { console.error(e); }
            }

            if (successCount > 0) {
                toastr.success(`${successCount} item(s) excluído(s) com sucesso!`);
                window._unifiedLoading = false;
                await loadUnifiedData();
            }
            window._pendingBulkDeleteItems = [];
        }

        function emptyAllUnified() {
            const msgEl = document.getElementById('empty-variable-message');
            if (msgEl) msgEl.textContent = 'Você realmente deseja esvaziar TODOS os itens de TODAS as variáveis? Esta ação não pode ser desfeita.';
            new bootstrap.Modal(document.getElementById('modal-confirm-empty-variable')).show();
        }

        async function executeEmptyAllUnified() {
            const modalEl = document.getElementById('modal-confirm-empty-variable');
            const m = bootstrap.Modal.getInstance(modalEl);
            if (m) m.hide();

            try {
                const res = await fetch('/dashboard/user/searches/variables/contents/empty-all', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    }
                });
                const data = await res.json();
                if (data.success) {
                    toastr.success('Toda a pesquisa foi zerada!');
                    window._unifiedLoading = false;
                    await loadUnifiedData();
                } else {
                    toastr.error(data.message || 'Erro ao zerar pesquisa.');
                }
            } catch (e) {
                console.error(e);
                toastr.error('Erro ao zerar pesquisa.');
            }
        }

        window._pendingUnifiedRemove = null;
        window._pendingBulkDeleteItems = [];

        function openUnifiedRemoveModal(itemId, variableId, source) {
            window._pendingUnifiedRemove = { itemId, variableId, source };
            window._pendingBulkDeleteItems = [];
            const msgEl = document.getElementById('bulk-delete-message');
            if (msgEl) msgEl.textContent = 'Você realmente deseja excluir este item?';
            new bootstrap.Modal(document.getElementById('modal-confirm-bulk-delete')).show();
        }

        async function executeUnifiedRemove() {
            const remove = window._pendingUnifiedRemove;
            if (!remove) return;

            const modalEl = document.getElementById('modal-confirm-bulk-delete');
            const m = bootstrap.Modal.getInstance(modalEl);
            if (m) m.hide();

            try {
                const res = await fetch('dashboard/user/searches/variables/contents/remove', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    },
                    body: JSON.stringify({ id: remove.itemId, source: remove.source || 'content' })
                });
                const data = await res.json();
                if (data.success || data.type === 'success') {
                    toastr.success(data.message || 'Item excluído com sucesso!');
                    window.unifiedAllItems = window.unifiedAllItems.filter(i => String(i.id) !== String(remove.itemId));
                    window.unifiedFilteredItems = window.unifiedFilteredItems.filter(i => String(i.id) !== String(remove.itemId));
                    const el = document.querySelector(`.unified-item[data-item-id="${remove.itemId}"]`);
                    if (el) el.remove();
                    const totalCount = document.getElementById('unified-total-count');
                    if (totalCount && window.unifiedFilteredItems.length > 0) {
                        totalCount.textContent = `${window.unifiedFilteredItems.length} item(s)`;
                    }
                } else {
                    toastr.error(data.message || 'Erro ao excluir item.');
                }
            } catch (e) {
                toastr.error('Erro ao processar a solicitação.');
                console.error(e);
            }
            window._pendingUnifiedRemove = null;
        }

        // Override handleActionUV for unified view
        function handleActionUV(type, id) {
            const url = type === 'approve'
                ? `/dashboard/user/searches/approve-pending-item/${id}`
                : `/dashboard/user/searches/reject-pending-item/${id}`;

            fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                }
            })
            .then(r => r.json())
            .then(data => {
                if (data.success || data.type === 'success') {
                    toastr.success(data.message || 'Ação realizada com sucesso!');

                    ['modal-approved-variable', 'modal-rejected-variable'].forEach(modalId => {
                        const el = document.getElementById(modalId);
                        if (el) { const m = bootstrap.Modal.getInstance(el); if (m) m.hide(); }
                    });

                    window.unifiedAllItems = window.unifiedAllItems.filter(i => String(i.id) !== String(id));
                    window._unifiedLoading = false;
                    loadUnifiedData();
                } else {
                    toastr.error(data.message || 'Erro ao processar ação.');
                }
            })
            .catch(e => {
                toastr.error('Erro ao processar a solicitação.');
                console.error(e);
            });
        }

        function setAttributeApprove(id) {
            document.querySelectorAll('.user_variable_approve_confirm').forEach(btn => {
                btn.setAttribute('data-id', id);
            });
        }

        function setAttributeReject(id) {
            document.querySelectorAll('.user_variable_reject_confirm').forEach(btn => {
                btn.setAttribute('data-id', id);
            });
        }

        function openAddVariableModal(id, label) {
            const modalVariableId = document.getElementById('modalVariableId');
            const modalVariableLabel = document.getElementById('modalVariableLabel');
            const pendingVariablesList = document.getElementById('pendingVariablesList');
            const variableValue = document.getElementById('variableValue');

            if (modalVariableId) modalVariableId.value = id;
            if (modalVariableLabel) modalVariableLabel.textContent = label;
            if (pendingVariablesList) pendingVariablesList.innerHTML = '';
            if (variableValue) variableValue.value = '';

            new bootstrap.Modal(document.getElementById('addVariableModal')).show();
        }

        // Override addVariableToDb to reload unified data after add
        async function addVariableToDb() {
            try {
                const res = await fetch('dashboard/user/searches/variables/contents/add', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    },
                    body: JSON.stringify({
                        id: document.getElementById('modalVariableId').value,
                        value: document.getElementById('variableValue').value
                    })
                });
                const data = await res.json();

                if (data.type === 'success') {
                    toastr.success(data.message);
                    document.getElementById('variableValue').value = '';
                    const modal = bootstrap.Modal.getInstance(document.getElementById('addVariableModal'));
                    if (modal) modal.hide();
                    window._unifiedLoading = false;
                    await loadUnifiedData();
                } else {
                    toastr.error(data.message || 'Erro ao adicionar conteúdo');
                }
            } catch (e) {
                toastr.error('Erro ao processar a solicitação.');
                console.error(e);
            }
        }

        // Setup event listeners for modals and infinite scroll
        document.addEventListener('DOMContentLoaded', function () {
            // Fallback: if my-research tab is active but data hasn't loaded yet, trigger load
            const myResearchPane = document.getElementById('my-research');
            if (myResearchPane && myResearchPane.classList.contains('active')) {
                if (!window._unifiedLoading && window.unifiedAllItems.length === 0) {
                    loadUnifiedData();
                }
            }

            // Confirm bulk delete / single remove
            const confirmBulkBtn = document.getElementById('confirm-bulk-delete-btn');
            if (confirmBulkBtn) {
                confirmBulkBtn.addEventListener('click', function () {
                    if (window._pendingBulkDeleteItems && window._pendingBulkDeleteItems.length > 0) {
                        executeBulkDeleteUnified();
                    } else if (window._pendingUnifiedRemove) {
                        executeUnifiedRemove();
                    }
                });
            }

            // Confirm empty all
            const confirmEmptyBtn = document.getElementById('confirm-empty-variable-btn');
            if (confirmEmptyBtn) {
                confirmEmptyBtn.addEventListener('click', function () {
                    executeEmptyAllUnified();
                });
            }

            // Infinite scroll observer
            const sentinel = document.getElementById('unified-scroll-sentinel');
            if (sentinel) {
                new IntersectionObserver((entries) => {
                    if (entries[0].isIntersecting && !window.unifiedState.groupBy) {
                        renderNextUnifiedPage();
                    }
                }, { threshold: 0.1 }).observe(sentinel);
            }
        });
    