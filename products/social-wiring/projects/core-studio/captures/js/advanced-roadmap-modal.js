/**
 * Advanced Roadmap Modal Component
 *
 * Componente reutilizável para criação de roteiros avançados com IA.
 * Suporta dois modos: simples (com observações) e avançado (com perguntas personalizadas)
 *
 * Dependências:
 * - jQuery
 * - Bootstrap 5
 * - Toastr (para notificações)
 *
 * Uso:
 * 1. Incluir o componente Blade: <x-advanced-roadmap-modal />
 * 2. Chamar para abrir: AdvancedRoadmapModal.open(headlineId, headlineText)
 * 3. Adicionar listener para cliques:
 *    $(document).on('click', '.btn-advanced-roadmap', function() {
 *        AdvancedRoadmapModal.open($(this).data('headline-id'), $(this).data('headline'));
 *    });
 */

const AdvancedRoadmapModal = (function() {
    'use strict';

    // Variáveis privadas
    let generatedQuestions = [];
    let pollingTimeout = null;
    let isPollingActive = false;
    let articleProgressShown = false;
    let articleMessageActive = false;
    let articleMessageTimeout = null;
    let initialProgressAnimation = null;
    let initialProgressValue = 0;
    const MAX_SELECTED_LINKS_PER_CATEGORY = 2; // Máximo de links que podem ser selecionados por categoria/item_pt

    // Step atual do formulário (1, 2 ou 3)
    let currentStep = 1;

    // Pesquisar na web (step 3): resultados e seleção (persiste ao mudar busca)
    let serperOrganicResults = [];
    let serperSelectedItems = []; // { link, title, snippet }
    /** Query efetiva enviada ao Serper na última busca (traduzida ou não), para enviar no submit */
    let lastSerperQuerySent = null;

    const MAX_SOURCE_LINKS = 4;

    /**
     * Inicializar o modal
     */
    function init() {
        // Listener para parar polling quando o modal for fechado
        document.addEventListener('hidden.bs.modal', function(e) {
            if (e.target.id === 'advancedRoadmapModal') {
                stopPolling();
                if (window.AdvancedRoadmapLibrary) {
                    window.AdvancedRoadmapLibrary.resetState();
                }
            }
        });

        // Step 3: seleção de fonte (links / none / serper) + vídeo da biblioteca
        document.addEventListener('click', function (e) {
            if (e.target.id === 'btnOpenLibrary' || e.target.closest('#btnOpenLibrary')) {
                if (window.AdvancedRoadmapLibrary && typeof window.AdvancedRoadmapLibrary.open === 'function') {
                    window.AdvancedRoadmapLibrary.open();
                } else {
                    console.error('[AdvancedRoadmap] AdvancedRoadmapLibrary não carregado.');
                }
                return;
            }
            const card = e.target.closest('.roadmap-source-card');
            if (card && card.getAttribute('data-source')) {
                selectSourceType(card.getAttribute('data-source'));
            }
            if (e.target.id === 'btnAddMoreLinks' || e.target.closest('#btnAddMoreLinks')) {
                addMoreLinkField();
            }
            if (e.target.id === 'btnSerperSearch' || e.target.closest('#btnSerperSearch')) {
                runSerperSearch();
            }
            const removeBtn = e.target.closest('.btn-remove-link');
            if (removeBtn) {
                const group = removeBtn.closest('.input-group');
                const container = group && group.parentElement;
                if (group) group.remove();
                if (container) {
                    const btnAdd = document.getElementById('btnAddMoreLinks');
                    const n = container.querySelectorAll('.roadmap-link-input').length;
                    if (btnAdd && n < MAX_SOURCE_LINKS) btnAdd.style.display = '';
                }
            }
        });
        document.addEventListener('change', function (e) {
            const cb = e.target.closest('.serper-result-checkbox');
            if (cb) toggleSerperSelection(cb);
            const sel = document.getElementById('selectCoreForRoadmap');
            if (sel && e.target === sel) {
                const hid = document.getElementById('roadmapCoreId');
                if (hid) hid.value = sel.value || '';
            }
        });
        document.addEventListener('click', function (e) {
            const btn = e.target.closest('.btn-remove-selected');
            if (btn && btn.getAttribute('data-link')) {
                removeSerperSelectedByUrl(btn.getAttribute('data-link'));
            }
            if (e.target.id === 'btnTranslateSerperResults' || e.target.closest('#btnTranslateSerperResults')) {
                translateSerperResults();
            }
            const clearVideoBtn = e.target.closest('[data-action="clear-selected-video"]');
            if (clearVideoBtn) {
                e.preventDefault();
                e.stopPropagation();
                if (window.AdvancedRoadmapLibrary && typeof window.AdvancedRoadmapLibrary.clearSelectedVideo === 'function') {
                    window.AdvancedRoadmapLibrary.clearSelectedVideo();
                } else {
                    const viralVideoEl = document.getElementById('selectedViralVideoId');
                    if (viralVideoEl) viralVideoEl.value = '';
                    const badgeEl = document.getElementById('selectedVideoBadge');
                    if (badgeEl) {
                        badgeEl.style.setProperty('display', 'none', 'important');
                        badgeEl.classList.add('d-none');
                        badgeEl.classList.remove('d-flex');
                    }
                }
            }
        });
    }

    /**
     * Abrir o modal
     */
    function open(headlineId, headlineText, editable = false) {
        // Preencher o modal
        const headlineField = document.getElementById('advancedRoadmapHeadline');
        if (!headlineField) {
            console.error('Elemento advancedRoadmapHeadline não encontrado');
            return;
        }
        headlineField.value = headlineText ? decodeURIComponent(headlineText) : '';
        headlineField.disabled = !editable;
        if (headlineField.hasAttribute('readonly') && !editable) {
            headlineField.removeAttribute('readonly');
        }
        if (!editable && headlineText) {
            headlineField.setAttribute('readonly', 'readonly');
        }

        const headlineIdField = document.getElementById('advancedRoadmapHeadlineId');
        if (headlineIdField) {
            headlineIdField.value = headlineId || '';
        }
        const aiField = document.getElementById('advancedRoadmapAI');
        if (aiField) {
            aiField.value = 'claude';
        }
        const chatResourceIdField = document.getElementById('advancedRoadmapChatResourceId');
        if (chatResourceIdField) {
            chatResourceIdField.value = '';
        }
        const resourceTypeField = document.getElementById('advancedRoadmapChatResourceType');
        const saveToField = document.getElementById('saveToTable');
        if (resourceTypeField && saveToField) {
            resourceTypeField.value = saveToField.value || resourceTypeField.value || 'eng_reversa_headlines';
        }

        currentStep = 1;
        const observationsField = document.getElementById('advancedRoadmapObservations');
        if (observationsField) {
            observationsField.value = '';
        }
        resetStep3Source();
        selectSourceType('none');

        const titleEl = document.getElementById('advancedRoadmapModalLabel');
        if (titleEl) titleEl.textContent = 'Roteiro Avançado';
        const isReprocessEl = document.getElementById('roadmapIsReprocess');
        if (isReprocessEl) isReprocessEl.value = '0';

        showState('form');
        const modal = new bootstrap.Modal(document.getElementById('advancedRoadmapModal'));
        modal.show();
    }

    /**
     * Resetar seleção e campos de fonte (links / none / serper) e vídeo da biblioteca
     */
    function resetStep3Source() {
        if (window.AdvancedRoadmapLibrary && typeof window.AdvancedRoadmapLibrary.clearSelectedVideo === 'function') {
            window.AdvancedRoadmapLibrary.clearSelectedVideo();
        } else {
            const viralVideoEl = document.getElementById('selectedViralVideoId');
            if (viralVideoEl) viralVideoEl.value = '';
            const badgeEl = document.getElementById('selectedVideoBadge');
            if (badgeEl) {
                badgeEl.style.display = 'none !important';
                badgeEl.classList.add('d-none');
                badgeEl.classList.remove('d-flex');
            }
        }

        const typeField = document.getElementById('roadmapSourceType');
        const pubmedField = document.getElementById('roadmapUsePubmed');
        if (typeField) typeField.value = '';
        if (pubmedField) pubmedField.value = '0';

        document.querySelectorAll('.roadmap-source-card').forEach(function (card) {
            if (card) {
                card.classList.remove('roadmap-source-selected');
                card.style.border = '';
            }
        });

        const below = document.getElementById('roadmapSourceFieldsBelow');
        if (below) below.style.display = 'none';
        const linksPanel = document.getElementById('sourceLinksPanel');
        if (linksPanel) linksPanel.style.display = 'none';
        const serperPanel = document.getElementById('sourceSerperPanel');
        if (serperPanel) serperPanel.style.display = 'none';

        const serperQuery = document.getElementById('serperQueryInput');
        if (serperQuery) serperQuery.value = '';
        const serperPubmed = document.getElementById('serperUsePubmed');
        if (serperPubmed) serperPubmed.checked = false;
        const serperSearchInPt = document.getElementById('serperSearchInPortuguese');
        if (serperSearchInPt) serperSearchInPt.checked = false;
        lastSerperQuerySent = null;
        const resultsWrap = document.getElementById('serperResultsWrap');
        if (resultsWrap) resultsWrap.style.display = 'none';
        const resultsContainer = document.getElementById('serperResultsContainer');
        if (resultsContainer) resultsContainer.innerHTML = '';
        const loadingState = document.getElementById('serperLoadingState');
        if (loadingState) loadingState.style.display = 'none';
        const emptyState = document.getElementById('serperEmptyState');
        if (emptyState) emptyState.style.display = 'block';
        const serperSelectedWrap = document.getElementById('serperSelectedWrap');
        if (serperSelectedWrap) serperSelectedWrap.style.display = 'none';
        const serperSelectedContainer = document.getElementById('serperSelectedContainer');
        if (serperSelectedContainer) serperSelectedContainer.innerHTML = '';
        serperOrganicResults = [];
        serperSelectedItems = [];

        const selectCore = document.getElementById('selectCoreForRoadmap');
        if (selectCore) selectCore.value = '';
        const coreIdHidden = document.getElementById('roadmapCoreId');
        if (coreIdHidden) coreIdHidden.value = '';

        const btnCreate = document.getElementById('btnCreateRoadmap');
        if (btnCreate) btnCreate.style.display = 'none';

        const container = document.getElementById('sourceLinksContainer');
        const btnAdd = document.getElementById('btnAddMoreLinks');
        if (!container) return;
        const first = document.createElement('div');
        first.className = 'input-group input-group-sm mb-2';
        first.innerHTML = '<input type="url" class="form-control form-control-sm roadmap-input roadmap-link-input" placeholder="https://…" data-index="0"><button type="button" class="btn btn-outline-danger btn-sm btn-remove-link" data-index="0" style="display: none;" title="Remover">×</button>';
        container.innerHTML = '';
        container.appendChild(first);
        if (btnAdd) {
            container.appendChild(btnAdd);
            btnAdd.style.display = '';
        }
    }

    /**
     * Selecionar fonte (links | none | serper). Só seleção; criar em "Criar Roteiro".
     */
    function selectSourceType(source) {
        const typeField = document.getElementById('roadmapSourceType');
        if (typeField) typeField.value = source;

        document.querySelectorAll('.roadmap-source-card').forEach(function (card) {
            if (!card) return;
            const isSelected = card.getAttribute('data-source') === source;
            card.classList.toggle('roadmap-source-selected', isSelected);
            card.style.border = '';
        });

        const below = document.getElementById('roadmapSourceFieldsBelow');
        const linksPanel = document.getElementById('sourceLinksPanel');
        const serperPanel = document.getElementById('sourceSerperPanel');
        const showBelow = source === 'links' || source === 'serper';
        if (below) below.style.display = showBelow ? 'block' : 'none';
        if (linksPanel) linksPanel.style.display = source === 'links' ? 'block' : 'none';
        if (serperPanel) serperPanel.style.display = source === 'serper' ? 'block' : 'none';

        if (source === 'serper') {
            const emptyEl = document.getElementById('serperEmptyState');
            const wrapEl = document.getElementById('serperResultsWrap');
            const selWrap = document.getElementById('serperSelectedWrap');
            if (emptyEl) emptyEl.style.display = serperOrganicResults.length ? 'none' : 'block';
            if (wrapEl) wrapEl.style.display = serperOrganicResults.length ? 'flex' : 'none';
            if (selWrap) selWrap.style.display = serperSelectedItems.length ? 'block' : 'none';
            renderSerperSelected();
        }

        const btnCreate = document.getElementById('btnCreateRoadmap');
        if (btnCreate) btnCreate.style.display = source ? 'inline-flex' : 'none';
    }

    /**
     * Adicionar mais um campo de link (Usar link específico). Máximo MAX_SOURCE_LINKS.
     */
    function addMoreLinkField() {
        const container = document.getElementById('sourceLinksContainer');
        if (!container) return;
        const inputs = container.querySelectorAll('.roadmap-link-input');
        if (inputs.length >= MAX_SOURCE_LINKS) {
            toastr.warning('Máximo de ' + MAX_SOURCE_LINKS + ' links.');
            return;
        }
        const index = inputs.length;
        const div = document.createElement('div');
        div.className = 'input-group input-group-sm mb-2';
        div.innerHTML = '<input type="url" class="form-control form-control-sm roadmap-input roadmap-link-input" placeholder="https://…" data-index="' + index + '"><button type="button" class="btn btn-outline-danger btn-sm btn-remove-link" data-index="' + index + '" title="Remover">×</button>';
        const btnAdd = document.getElementById('btnAddMoreLinks');
        container.insertBefore(div, btnAdd);
        const removeBtn = div.querySelector('.btn-remove-link');
        if (removeBtn) removeBtn.style.display = 'inline-block';
        if (inputs.length === 1) {
            const firstRemove = container.querySelector('.btn-remove-link[data-index="0"]');
            if (firstRemove) firstRemove.style.display = 'inline-block';
        }
        if (container.querySelectorAll('.roadmap-link-input').length >= MAX_SOURCE_LINKS && btnAdd) {
            btnAdd.style.display = 'none';
        }
    }

    function runSerperSearch() {
        const queryInput = document.getElementById('serperQueryInput');
        const query = queryInput ? queryInput.value.trim() : '';
        if (!query) {
            toastr.warning('Digite o que deseja pesquisar.');
            return;
        }

        const loadingEl = document.getElementById('serperLoadingState');
        const emptyEl = document.getElementById('serperEmptyState');
        const wrapEl = document.getElementById('serperResultsWrap');
        const containerEl = document.getElementById('serperResultsContainer');
        const btnSearch = document.getElementById('btnSerperSearch');

        if (loadingEl) loadingEl.style.display = 'block';
        if (emptyEl) emptyEl.style.display = 'none';
        if (wrapEl) wrapEl.style.display = 'none';
        if (btnSearch) btnSearch.disabled = true;
        if (containerEl) containerEl.innerHTML = '';

        serperOrganicResults = [];

        var usePubmed = document.getElementById('serperUsePubmed') && document.getElementById('serperUsePubmed').checked;
        var searchInPortuguese = document.getElementById('serperSearchInPortuguese') && document.getElementById('serperSearchInPortuguese').checked;
        var translateUrl = window.AdvancedRoadmapModalConfig?.routes?.translateSearchQuery
            || '/dashboard/user/headlines/suggested/advanced-roadmap/translate-search-query';
        var directSearchUrl = window.AdvancedRoadmapModalConfig?.routes?.directSearch
            || '/dashboard/user/headlines/suggested/advanced-roadmap/direct-search';

        function doDirectSearch(queryToSend, gl, hl) {
            lastSerperQuerySent = queryToSend;
            $.ajax({
                url: directSearchUrl,
                type: 'POST',
                data: {
                    _token: window.AdvancedRoadmapModalConfig.csrfToken,
                    query: queryToSend,
                    gl: gl,
                    hl: hl
                },
                success: function(response) {
                    if (loadingEl) loadingEl.style.display = 'none';
                    if (btnSearch) btnSearch.disabled = false;

                    if (response.success && response.data && Array.isArray(response.data.organic) && response.data.organic.length) {
                        serperOrganicResults = response.data.organic;
                        renderSerperResults();
                        if (wrapEl) wrapEl.style.display = 'flex';
                        if (emptyEl) emptyEl.style.display = 'none';
                        renderSerperSelected();
                        var selWrap = document.getElementById('serperSelectedWrap');
                        if (selWrap) selWrap.style.display = serperSelectedItems.length ? 'block' : 'none';
                    } else {
                        serperOrganicResults = [];
                        toastr.warning('Nenhum resultado encontrado.');
                        if (emptyEl) emptyEl.style.display = 'block';
                    }
                },
                error: function(xhr, status, error) {
                    if (loadingEl) loadingEl.style.display = 'none';
                    if (btnSearch) btnSearch.disabled = false;
                    toastr.error('Erro ao buscar na web. Tente novamente.');
                }
            });
        }

        function performSearch(queryToSend, gl, hl) {
            doDirectSearch(queryToSend, gl, hl);
        }

        // PubMed: sempre traduzir e buscar em inglês (EUA)
        if (usePubmed) {
            $.ajax({
                url: translateUrl,
                type: 'POST',
                data: {
                    _token: window.AdvancedRoadmapModalConfig.csrfToken,
                    query: query
                },
                success: function(res) {
                    if (res.success && res.data && res.data.query_en) {
                        var q = res.data.query_en.trim() + ' site:pubmed.ncbi.nlm.nih.gov';
                        performSearch(q, 'us', 'en');
                    } else {
                        if (loadingEl) loadingEl.style.display = 'none';
                        if (btnSearch) btnSearch.disabled = false;
                        toastr.error(res.message || 'Erro ao traduzir busca.');
                    }
                },
                error: function(xhr) {
                    if (loadingEl) loadingEl.style.display = 'none';
                    if (btnSearch) btnSearch.disabled = false;
                    toastr.error('Erro ao traduzir busca. Tente novamente.');
                }
            });
            return;
        }

        // Padrão: buscar em inglês (traduzir com GPT-4o-mini)
        if (!searchInPortuguese) {
            $.ajax({
                url: translateUrl,
                type: 'POST',
                data: {
                    _token: window.AdvancedRoadmapModalConfig.csrfToken,
                    query: query
                },
                success: function(res) {
                    if (res.success && res.data && res.data.query_en) {
                        var q = res.data.query_en.trim();
                        performSearch(q, 'us', 'en');
                    } else {
                        if (loadingEl) loadingEl.style.display = 'none';
                        if (btnSearch) btnSearch.disabled = false;
                        toastr.error(res.message || 'Erro ao traduzir busca.');
                    }
                },
                error: function(xhr) {
                    if (loadingEl) loadingEl.style.display = 'none';
                    if (btnSearch) btnSearch.disabled = false;
                    toastr.error('Erro ao traduzir busca. Tente novamente.');
                }
            });
            return;
        }

        // Opção "Quero buscar em português": busca direta em pt-br
        performSearch(query.trim(), 'br', 'pt-br');
    }

    function renderSerperResults() {
        const container = document.getElementById('serperResultsContainer');
        if (!container) return;
        container.innerHTML = '';
        const selectedUrls = serperSelectedItems.map(function (x) { return x.link; });
        serperOrganicResults.forEach(function (r, i) {
            const link = r.link || '#';
            const title = (r.title || 'Sem título').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            const snippet = (r.snippet || '').replace(/</g, '&lt;').replace(/>/g, '&gt;').substring(0, 200);
            const id = 'serper_result_' + i;
            const titleId = 'serper_title_' + i;
            const snippetId = 'serper_snippet_' + i;
            const isSelected = selectedUrls.indexOf(link) !== -1;
            const div = document.createElement('div');
            div.className = 'roadmap-serper-result-item';
            div.innerHTML = '<div class="form-check flex-grow-1">' +
                '<input class="form-check-input serper-result-checkbox" type="checkbox" id="' + id + '" data-link="' + (link.replace(/"/g, '&quot;')) + '" data-title="' + (title.replace(/"/g, '&quot;')) + '" data-snippet="' + (snippet.replace(/"/g, '&quot;')) + '"' + (isSelected ? ' checked' : '') + '>' +
                '<label class="form-check-label w-100" for="' + id + '">' +
                '<div class="result-title" id="' + titleId + '">' +
                '<a href="' + link + '" target="_blank" rel="noopener" onclick="event.stopPropagation()">' + title + ' <span class="opacity-50">↗</span></a>' +
                '</div>' +
                (snippet ? '<div class="result-snippet" id="' + snippetId + '">' + snippet + (r.snippet && r.snippet.length > 200 ? '…' : '') + '</div>' : '') +
                '</label></div>';
            container.appendChild(div);
        });
        renderSerperSelected();
    }

    /**
     * Traduzir resultados da pesquisa (step 3) para português via translateSearchResults.
     */
    function translateSerperResults() {
        const checkboxes = document.querySelectorAll('.serper-result-checkbox');
        if (!checkboxes.length) {
            toastr.warning('Nenhum resultado para traduzir.');
            return;
        }

        const btn = document.getElementById('btnTranslateSerperResults');
        const origHtml = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span> Traduzindo…';
        }

        const translateUrl = window.AdvancedRoadmapModalConfig?.routes?.translateSearchResults
            || '/dashboard/user/headlines/suggested/advanced-roadmap/translate-search-results';

        const results = [];
        checkboxes.forEach(function (cb, i) {
            const title = (cb.getAttribute('data-title') || '').replace(/&quot;/g, '"');
            const snippet = (cb.getAttribute('data-snippet') || '').replace(/&quot;/g, '"');
            if (title || snippet) {
                results.push({
                    checkbox: cb,
                    titleId: 'serper_title_' + i,
                    snippetId: 'serper_snippet_' + i,
                    originalTitle: title,
                    originalSnippet: snippet
                });
            }
        });

        if (results.length === 0) {
            if (btn) { btn.disabled = false; btn.innerHTML = origHtml; }
            toastr.warning('Nenhum resultado para traduzir.');
            return;
        }

        var completed = 0;
        var hasError = false;

        function checkDone() {
            completed++;
            if (completed < results.length) return;
            if (btn) { btn.disabled = false; btn.innerHTML = origHtml; }
            if (hasError) toastr.warning('Alguns resultados não puderam ser traduzidos.');
            else toastr.success(results.length + ' resultado(s) traduzido(s).');
        }

        results.forEach(function (r) {
            $.ajax({
                url: translateUrl,
                type: 'POST',
                data: {
                    _token: window.AdvancedRoadmapModalConfig.csrfToken,
                    title: r.originalTitle,
                    snippet: r.originalSnippet
                },
                success: function (res) {
                    if (res.success && res.data) {
                        if (res.data.title) {
                            var el = document.getElementById(r.titleId);
                            if (el) {
                                var a = el.querySelector('a');
                                if (a) a.innerHTML = res.data.title + ' <span class="opacity-50">↗</span>';
                                else el.textContent = res.data.title;
                            }
                            r.checkbox.setAttribute('data-title', (res.data.title || '').replace(/"/g, '&quot;'));
                        }
                        if (res.data.snippet) {
                            var sel = document.getElementById(r.snippetId);
                            if (sel) sel.textContent = res.data.snippet;
                            r.checkbox.setAttribute('data-snippet', res.data.snippet.replace(/"/g, '&quot;'));
                        }
                    }
                    checkDone();
                },
                error: function () {
                    hasError = true;
                    checkDone();
                }
            });
        });
    }

    function toggleSerperSelection(cb) {
        const link = cb.getAttribute('data-link') || '';
        const title = cb.getAttribute('data-title') || '';
        const snippet = cb.getAttribute('data-snippet') || '';
        var idx = -1;
        for (var i = 0; i < serperSelectedItems.length; i++) {
            if (serperSelectedItems[i].link === link) { idx = i; break; }
        }
        if (cb.checked) {
            if (idx === -1) {
                if (serperSelectedItems.length >= MAX_SOURCE_LINKS) {
                    cb.checked = false;
                    toastr.warning('Máximo de ' + MAX_SOURCE_LINKS + ' links selecionados.');
                    return;
                }
                serperSelectedItems.push({ link: link, title: title, snippet: snippet });
            }
        } else {
            if (idx !== -1) serperSelectedItems.splice(idx, 1);
        }
        renderSerperSelected();
        var selWrap = document.getElementById('serperSelectedWrap');
        if (selWrap) selWrap.style.display = serperSelectedItems.length ? 'block' : 'none';
    }

    function removeSerperSelectedByUrl(url) {
        serperSelectedItems = serperSelectedItems.filter(function (x) { return x.link !== url; });
        renderSerperSelected();
        var selWrap = document.getElementById('serperSelectedWrap');
        if (selWrap) selWrap.style.display = serperSelectedItems.length ? 'block' : 'none';
        document.querySelectorAll('.serper-result-checkbox').forEach(function (c) {
            if ((c.getAttribute('data-link') || '') === url) c.checked = false;
        });
    }

    function renderSerperSelected() {
        const container = document.getElementById('serperSelectedContainer');
        const badge = document.getElementById('serperSelectedCount');
        if (!container) return;
        container.innerHTML = '';
        serperSelectedItems.forEach(function (item) {
            const title = (item.title || 'Sem título').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            const snippet = (item.snippet || '').replace(/</g, '&lt;').replace(/>/g, '&gt;').substring(0, 120);
            const div = document.createElement('div');
            div.className = 'roadmap-serper-selected-item';
            div.innerHTML = '<div class="flex-grow-1">' +
                '<div class="result-title"><a href="' + (item.link || '#') + '" target="_blank" rel="noopener" onclick="event.stopPropagation()">' + title + ' <span class="opacity-50">↗</span></a></div>' +
                (snippet ? '<div class="result-snippet">' + snippet + (item.snippet && item.snippet.length > 120 ? '…' : '') + '</div>' : '') +
                '</div>' +
                '<button type="button" class="btn btn-sm btn-outline-danger btn-remove-selected" data-link="' + (item.link || '').replace(/"/g, '&quot;') + '" title="Remover">×</button>';
            container.appendChild(div);
        });
        if (badge) badge.textContent = serperSelectedItems.length;
    }

    /**
     * Enviar formulário dos 3 steps (backend decide o modo)
     */
    function submitRoadmapSteps() {
        const headlineId = document.getElementById('advancedRoadmapHeadlineId')?.value || '';
        const headlineText = document.getElementById('advancedRoadmapHeadline')?.value?.trim() || '';
        const observations = document.getElementById('advancedRoadmapObservations')?.value?.trim() || '';
        const sourceType = document.getElementById('roadmapSourceType')?.value || '';

        if (!headlineId && !headlineText) {
            toastr.warning('Informe a headline.');
            return;
        }
        if (!sourceType) {
            toastr.warning('Escolha de onde usar as informações (link específico, IA pensar ou pesquisar dinamicamente).');
            return;
        }

        if (sourceType === 'links') {
            const linkInputs = document.querySelectorAll('.roadmap-link-input');
            let links = Array.from(linkInputs).map(function (input) { return input.value.trim(); }).filter(Boolean);
            if (links.length === 0) {
                toastr.warning('Adicione pelo menos um link.');
                return;
            }
            if (links.length > MAX_SOURCE_LINKS) links = links.slice(0, MAX_SOURCE_LINKS);
        }
        if (sourceType === 'serper') {
            const query = document.getElementById('serperQueryInput')?.value?.trim() || '';
            if (!query) {
                toastr.warning('Digite algo e clique em Pesquisar.');
                return;
            }
            if (serperSelectedItems.length === 0) {
                toastr.warning('Selecione pelo menos um resultado da pesquisa.');
                return;
            }
        }

        const usePubmed = document.getElementById('serperUsePubmed')?.checked ? '1' : '0';
        const roadmapUsePubmed = document.getElementById('roadmapUsePubmed');
        if (roadmapUsePubmed) roadmapUsePubmed.value = usePubmed;

        const saveToTable = document.getElementById('saveToTable')?.value || 'user_roadmaps';
        const requestData = {
            _token: window.AdvancedRoadmapModalConfig.csrfToken,
            ai_provider: document.getElementById('advancedRoadmapAI')?.value || 'claude',
            mode: 'steps',
            save_to: saveToTable,
            roadmap_source_type: sourceType,
            observations: observations,
            roadmap_use_pubmed: usePubmed
        };
        if (headlineId) requestData.headline_id = headlineId;
        else requestData.headline_text = headlineText;

        if (sourceType === 'links') {
            const linkInputs = document.querySelectorAll('.roadmap-link-input');
            const raw = Array.from(linkInputs).map(function (input) { return input.value.trim(); }).filter(Boolean);
            requestData.source_links = raw.slice(0, MAX_SOURCE_LINKS);
        }
        if (sourceType === 'serper') {
            requestData.serper_query = (lastSerperQuerySent || document.getElementById('serperQueryInput')?.value?.trim() || '').trim();
            requestData.serper_search_in_portuguese = document.getElementById('serperSearchInPortuguese')?.checked ? '1' : '0';
            requestData.source_links = serperSelectedItems.slice(0, MAX_SOURCE_LINKS).map(function (x) { return x.link; });
        }
        const coreId = document.getElementById('roadmapCoreId')?.value || document.getElementById('selectCoreForRoadmap')?.value || '';
        if (coreId) requestData.core_id = coreId;

        const viralVideoId = document.getElementById('selectedViralVideoId')?.value?.trim() || '';
        if (viralVideoId) requestData.viral_video_id = viralVideoId;
        requestData.duration_minutes = document.getElementById('roadmapDurationMinutes')?.value || 'auto';
        requestData.is_reprocess = document.getElementById('roadmapIsReprocess')?.value === '1' ? 1 : 0;

        showState('creating');
        $.ajax({
            url: window.AdvancedRoadmapModalConfig.routes.store,
            type: 'POST',
            data: requestData,
            success: function (data) {
                if (data.success) {
                    const pollingId = data.headline_id || data.roadmap_id || headlineId;
                    if (pollingId) startLongPolling(pollingId);
                    toastr.success('Roteiro enviado para processamento!');
                } else {
                    showState('form');
                    toastr.error(data.message || 'Erro ao criar roteiro.');
                }
            },
            error: function (xhr) {
                showState('form');
                toastr.error('Erro ao criar roteiro.');
                console.error(xhr);
            }
        });
    }

    /**
     * Verificar se já existe roteiro avançado
     */
    function checkExistingRoadmap(headlineId, headlineText) {
        console.log('[AdvancedRoadmap] Verificando se existe roteiro para headline_id:', headlineId);

        $.ajax({
            url: window.AdvancedRoadmapModalConfig.routes.show.replace('__ID__', headlineId),
            type: 'GET',
            data: {
                headline_id: headlineId
            },
            success: function(data) {
                console.log('[AdvancedRoadmap] Resposta da verificação:', {
                    success: data.success,
                    has_roadmap: !!data.roadmap_advanced,
                    status: data.status,
                    roadmap_length: data.roadmap_advanced ? data.roadmap_advanced.length : 0,
                    headline_id_usado: headlineId
                });

                if(data.success && data.roadmap_advanced && data.status === 'completed') {
                    // Roteiro já existe - mostrar resultado
                    console.log('[AdvancedRoadmap] ✅ Roteiro existente encontrado! Mostrando resultado');
                    document.getElementById('advancedRoadmapHeadlineResult').value = headlineText ? decodeURIComponent(headlineText) : '';
                    document.getElementById('advancedRoadmapResult').value = data.roadmap_advanced;
                    document.getElementById('advancedRoadmapHeadlineId').value = headlineId || '';
                    const chatResourceId = data.roadmap_id || data.headline_id || headlineId || '';
                    document.getElementById('advancedRoadmapChatResourceId').value = chatResourceId;
                    const idForUpdateEl = document.getElementById('advancedRoadmapIdForUpdate');
                    if (idForUpdateEl) idForUpdateEl.value = data.roadmap_id || '';
                    const resourceTypeField = document.getElementById('advancedRoadmapChatResourceType');
                    const saveToField = document.getElementById('saveToTable');
                    if (resourceTypeField) {
                        resourceTypeField.value = data.roadmap_source || (saveToField && saveToField.value) || resourceTypeField.value || 'eng_reversa_headlines';
                    }

                    // Verificar se há dados de pesquisa
                    if(data.search_id && data.search_text) {
                        console.log('[AdvancedRoadmap] Dados de pesquisa encontrados no roteiro existente');
                        // Mostrar a aba de fontes
                        document.getElementById('sources-tab-li').style.display = 'block';

                        // Formatar e exibir o search_text
                        let searchTextFormatted = data.search_text.replace(/\n/g, '<br>');
                        document.getElementById('advancedSearchSourcesContent').innerHTML = searchTextFormatted;
                    } else {
                        // Esconder a aba de fontes se não houver dados
                        document.getElementById('sources-tab-li').style.display = 'none';
                        document.getElementById('advancedSearchSourcesContent').innerHTML = '';
                    }

                    showState('result');
                } else {
                    // Roteiro não existe ou não está completo - mostrar formulário
                    console.log('[AdvancedRoadmap] ❌ Roteiro não existe ou incompleto. Mostrando formulário');
                    showState('form');
                }
            },
            error: function(xhr) {
                console.error('[AdvancedRoadmap] Erro ao verificar roteiro:', xhr);
                // Em caso de erro, mostrar formulário
                showState('form');
            }
        });
    }

    /**
     * Abrir modal com headline customizada (editável)
     */
    function openWithCustomHeadline(initialHeadline = '') {
        open(null, initialHeadline, true);
    }

    /**
     * Abrir modal para reprocessar roteiro: preenche headline, instruções, cérebro, vídeo viral e fonte (link específico quando havia ERB ou links).
     * @param {Object} options - { headline, name, observations, brain_id, viral_id, params }
     * @param {Object} options.params - { observations, brain_id, core_id, viral_id, viral_video_id, roadmap_source_type, source_links, selected_links }
     */
    function openForReprocess(options) {
        if (!options) return;
        const headline = options.headline || options.name || '';
        const observations = (options.observations || (options.params && options.params.observations) || '').trim();
        const brainId = options.brain_id ?? options.params?.brain_id ?? options.params?.core_id ?? '';
        const viralId = options.viral_id ?? options.params?.viral_id ?? options.params?.viral_video_id ?? '';
        const params = options.params || {};

        open(null, headline, true);

        const isReprocessEl = document.getElementById('roadmapIsReprocess');
        if (isReprocessEl) isReprocessEl.value = '1';

        const modalTitleEl = document.getElementById('advancedRoadmapModalLabel');
        if (modalTitleEl && headline) {
            var titleHeadline = headline.length > 60 ? headline.substring(0, 60) + '...' : headline;
            modalTitleEl.textContent = 'Roteiro reprocessado: ' + titleHeadline;
        }

        const observationsField = document.getElementById('advancedRoadmapObservations');
        if (observationsField) observationsField.value = observations;

        const coreIdHidden = document.getElementById('roadmapCoreId');
        const selectCore = document.getElementById('selectCoreForRoadmap');
        if (coreIdHidden) coreIdHidden.value = brainId ? String(brainId) : '';
        if (selectCore) {
            const opt = selectCore.querySelector('option[value="' + brainId + '"]');
            if (opt) selectCore.value = String(brainId);
            else selectCore.value = coreIdHidden ? coreIdHidden.value : '';
        }

        const viralVideoEl = document.getElementById('selectedViralVideoId');
        const badgeEl = document.getElementById('selectedVideoBadge');
        const titleEl = document.getElementById('selectedVideoTitle');
        const statsEl = document.getElementById('selectedVideoStats');
        const viralVideo = options.viral_video || null;
        if (viralId && viralVideoEl) {
            viralVideoEl.value = String(viralId);
            if (badgeEl) {
                badgeEl.style.setProperty('display', 'flex', 'important');
                badgeEl.classList.remove('d-none');
                badgeEl.classList.add('d-flex');
            }
            if (titleEl) {
                if (viralVideo && (viralVideo.title || viralVideo.description)) {
                    var title = viralVideo.title || viralVideo.description || 'Vídeo selecionado';
                    titleEl.textContent = title.length > 50 ? title.substring(0, 50) + '...' : title;
                    titleEl.title = title;
                } else {
                    titleEl.textContent = 'Vídeo viral (ID: ' + viralId + ')';
                    titleEl.title = '';
                }
            }
            if (statsEl && viralVideo && (viralVideo.plays != null || viralVideo.likes != null)) {
                var fmt = function (n) { return n >= 1000000 ? (n / 1000000).toFixed(1) + 'M' : n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n); };
                var plays = viralVideo.plays || 0;
                var likes = viralVideo.likes || 0;
                statsEl.textContent = fmt(plays) + ' views • ' + fmt(likes) + ' likes';
            } else if (statsEl) {
                statsEl.textContent = '';
            }
        }

        const sourceType = params.roadmap_source_type || '';
        const sourceLinks = params.source_links || [];
        const selectedLinks = params.selected_links || [];
        let linkUrls = Array.isArray(sourceLinks) ? sourceLinks.slice() : [];
        if (linkUrls.length === 0 && Array.isArray(selectedLinks)) {
            linkUrls = selectedLinks.map(function (item) {
                return typeof item === 'string' ? item : (item && item.link) ? item.link : null;
            }).filter(Boolean);
        }
        if (sourceType === 'serper' || sourceType === 'links' || linkUrls.length > 0) {
            selectSourceType('links');
            const container = document.getElementById('sourceLinksContainer');
            const btnAdd = document.getElementById('btnAddMoreLinks');
            if (container && linkUrls.length > 0) {
                container.innerHTML = '';
                linkUrls.slice(0, MAX_SOURCE_LINKS).forEach(function (url, i) {
                    const div = document.createElement('div');
                    div.className = 'input-group input-group-sm mb-2';
                    div.innerHTML = '<input type="url" class="form-control form-control-sm roadmap-input roadmap-link-input" placeholder="https://…" data-index="' + i + '" value="' + (url || '').replace(/"/g, '&quot;') + '"><button type="button" class="btn btn-outline-danger btn-sm btn-remove-link" data-index="' + i + '" title="Remover">×</button>';
                    const removeBtn = div.querySelector('.btn-remove-link');
                    if (removeBtn) removeBtn.style.display = 'inline-block';
                    container.appendChild(div);
                });
                if (btnAdd) {
                    container.appendChild(btnAdd);
                    btnAdd.style.display = linkUrls.length >= MAX_SOURCE_LINKS ? 'none' : '';
                }
            }
        } else {
            selectSourceType('none');
        }
    }

    /**
     * Selecionar opção principal (manual ou automático)
     */
    function selectMainOption(mainOption) {
        const mainOptionsContainer = document.getElementById('mainOptionsContainer');
        const manualSubOptions = document.getElementById('manualSubOptions');
        const autoSearchDirectionField = document.getElementById('autoSearchDirectionField');
        const advancedSearchEnabled = document.getElementById('advancedSearchEnabled');
        const backBtn = document.getElementById('backToMainOptionsBtn');

        // Resetar sub-opções
        document.getElementById('selectedRoadmapOption').value = '';
        const optionSimpleObservations2 = document.getElementById('optionSimpleObservations');
        if (optionSimpleObservations2) {
            optionSimpleObservations2.style.border = '2px solid transparent';
        }
        const optionAdvancedQuestions2 = document.getElementById('optionAdvancedQuestions');
        if (optionAdvancedQuestions2) {
            optionAdvancedQuestions2.style.border = '2px solid transparent';
        }
        // Campo de observações agora está sempre visível no modo manual, não precisa esconder

        if (mainOption === 'library') {
            // Modo Biblioteca: Abrir biblioteca de vídeos virais
            console.log('[AdvancedRoadmap] Abrindo Biblioteca de Vídeos Virais');

            // Abrir biblioteca (fade out do formulário e fade in da biblioteca)
            if (window.AdvancedRoadmapLibrary) {
                window.AdvancedRoadmapLibrary.open();
            } else {
                console.error('[AdvancedRoadmap] AdvancedRoadmapLibrary não foi carregado!');
                toastr.error('Erro ao abrir biblioteca. Recarregue a página.');
            }

            return; // Não executar resto da lógica
        }

        // Esconder container de opções principais (só para manual e auto)
        mainOptionsContainer.style.display = 'none';

        // Mostrar botão voltar
        backBtn.style.display = 'inline-block';

        if (mainOption === 'manual') {
            // Modo Manual: Desativa busca e mostra sub-opções
            manualSubOptions.style.display = 'block';
            autoSearchDirectionField.style.display = 'none'; // Esconder campo de direcionamento
            advancedSearchEnabled.value = '0'; // Desativar busca avançada

            // Na v2, quando seleciona manual, automaticamente define como 'simple'
            // pois o campo de informações está sempre visível
            // Verificar se existe o card optionSimpleObservations (v1) ou se é v2 (campo direto)
            const optionSimpleObservations = document.getElementById('optionSimpleObservations');
            if (optionSimpleObservations) {
                // v1: tem os cards de sub-opção, não definir automaticamente
                document.getElementById('selectedRoadmapOption').value = '';
            } else {
                // v2: campo direto, definir automaticamente como 'simple'
                document.getElementById('selectedRoadmapOption').value = 'simple';
            }

            // Mostrar botão continuar (campos estão sempre visíveis agora)
            document.getElementById('createDefaultRoadmapBtn').style.display = 'none';
            document.getElementById('continueOptionBtn').style.display = 'inline-block';

            console.log('[AdvancedRoadmap] Modo Manual selecionado - Busca Avançada: DESATIVADA');
        } else if (mainOption === 'auto') {
            // Modo Automático: Ativa busca manual e esconde sub-opções
            manualSubOptions.style.display = 'none';
            autoSearchDirectionField.style.display = 'block'; // Mostrar interface de busca manual
            advancedSearchEnabled.value = '1'; // Ativar busca avançada

            // Inicializar primeira caixa de busca
            initializeManualSearch();

            // Mostrar botão continuar (agora que busca é manual)
            document.getElementById('createDefaultRoadmapBtn').style.display = 'none';
            document.getElementById('continueOptionBtn').style.display = 'inline-block';

            console.log('[AdvancedRoadmap] Modo Automático selecionado - Busca Manual: ATIVADA');
        }
    }

    /**
     * Voltar para as opções principais
     */
    function backToMainOptions() {
        const mainOptionsContainer = document.getElementById('mainOptionsContainer');
        const manualSubOptions = document.getElementById('manualSubOptions');
        const autoSearchDirectionField = document.getElementById('autoSearchDirectionField');
        const backBtn = document.getElementById('backToMainOptionsBtn');

        // Mostrar container de opções principais
        mainOptionsContainer.style.display = 'block';

        // Esconder botão voltar
        backBtn.style.display = 'none';

        // Esconder sub-opções
        manualSubOptions.style.display = 'none';
        autoSearchDirectionField.style.display = 'none';

        // Resetar campos
        document.getElementById('selectedRoadmapOption').value = '';
        document.getElementById('simpleObservationsText').value = '';

        // Limpar buscas manuais
        const manualSearchBoxesContainer = document.getElementById('manualSearchBoxesContainer');
        if (manualSearchBoxesContainer) {
            manualSearchBoxesContainer.innerHTML = '';
        }
        searchBoxCounter = 0;
        allManualSearchResults = {};
        const optionSimpleObservations3 = document.getElementById('optionSimpleObservations');
        if (optionSimpleObservations3) {
            optionSimpleObservations3.style.border = '2px solid transparent';
        }
        document.getElementById('optionAdvancedQuestions').style.border = '2px solid transparent';
        // Campo de observações agora está sempre visível no modo manual
        document.getElementById('advancedSearchEnabled').value = '0';

        // Resetar botões
        document.getElementById('createDefaultRoadmapBtn').style.display = 'none';
        document.getElementById('continueOptionBtn').style.display = 'none';

        // Resetar bordas dos cards principais
        document.getElementById('mainOptionManual').style.border = '3px solid transparent';
        document.getElementById('mainOptionAuto').style.border = '3px solid transparent';

        console.log('[AdvancedRoadmap] Voltou para opções principais');
    }

    /**
     * Selecionar sub-opção de criação (dentro do modo manual)
     */
    function selectOption(option) {
        // Armazenar a opção selecionada
        document.getElementById('selectedRoadmapOption').value = option;

        // Resetar estilo dos cards
        const optionSimpleObservations4 = document.getElementById('optionSimpleObservations');
        if (optionSimpleObservations4) {
            optionSimpleObservations4.style.border = '2px solid transparent';
        }
        document.getElementById('optionAdvancedQuestions').style.border = '0px solid transparent';

        // Destacar o card selecionado
        if (option === 'simple') {
            if (optionSimpleObservations4) {
                optionSimpleObservations4.style.border = '2px solid #206bc4';
            }
            // Mostrar campo de observações (v1)
            const simpleObservationsField = document.getElementById('simpleObservationsField');
            if (simpleObservationsField) {
                simpleObservationsField.style.display = 'block';
            }
        } else if (option === 'advanced') {
            // Bloquear seleção de advanced (temporariamente desabilitado)
            toastr.warning('Esta opção está temporariamente desabilitada. Use "Escrever Informações Diretamente" para criar seu roteiro.');
            document.getElementById('selectedRoadmapOption').value = '';
            return;
        }

        // Mostrar botão de continuar
        document.getElementById('continueOptionBtn').style.display = 'inline-block';
        document.getElementById('createDefaultRoadmapBtn').style.display = 'none';
    }

    /**
     * Selecionar provedor de busca (Perplexity, GPT ou GPT Deep)
     */
    function selectSearchProvider(provider) {
        // Atualizar campo hidden
        const searchProviderField = document.getElementById('searchProvider');
        if (searchProviderField) {
            searchProviderField.value = provider;
        }

        // Resetar estilo dos cards (se existirem)
        const searchProviderPerplexity = document.getElementById('searchProviderPerplexity');
        if (searchProviderPerplexity) {
            searchProviderPerplexity.style.border = '2px solid transparent';
        }
        const searchProviderGPT = document.getElementById('searchProviderGPT');
        if (searchProviderGPT) {
            searchProviderGPT.style.border = '2px solid transparent';
        }
        const searchProviderGPTDeep = document.getElementById('searchProviderGPTDeep');
        if (searchProviderGPTDeep) {
            searchProviderGPTDeep.style.border = '2px solid transparent';
        }

        // Marcar o radio correto (se existirem)
        const radioPerplexity = document.getElementById('radioPerplexity');
        if (radioPerplexity) {
            radioPerplexity.checked = (provider === 'perplexity');
        }
        const radioGPT = document.getElementById('radioGPT');
        if (radioGPT) {
            radioGPT.checked = (provider === 'gpt');
        }
        const radioGPTDeep = document.getElementById('radioGPTDeep');
        if (radioGPTDeep) {
            radioGPTDeep.checked = (provider === 'gpt-deep');
        }

        // Destacar o card selecionado e manter tipo de busca oculto (mas funcional)
        if (provider === 'perplexity' && searchProviderPerplexity) {
            searchProviderPerplexity.style.border = '2px solid #ae3ec9'; // purple
            // searchTypeField permanece oculto
            // Garantir que "completo" esteja selecionado por padrão
            selectSearchType('completo');
            console.log('[AdvancedRoadmap] Provedor Perplexity selecionado');
        } else if (provider === 'gpt' && searchProviderGPT) {
            searchProviderGPT.style.border = '2px solid #206bc4'; // blue
            // searchTypeField permanece oculto
            // Garantir que "completo" esteja selecionado por padrão
            selectSearchType('completo');
            console.log('[AdvancedRoadmap] Provedor GPT Search selecionado');
        } else if (provider === 'gpt-deep' && searchProviderGPTDeep) {
            searchProviderGPTDeep.style.border = '2px solid #f76707'; // orange
            // searchTypeField permanece oculto
            // Garantir que "completo" esteja selecionado por padrão
            selectSearchType('completo');
            console.log('[AdvancedRoadmap] Provedor GPT Deep Research selecionado [EXPERIMENTAL]');
        }
    }

    /**
     * Selecionar tipo de busca (resumo ou completo) - válido para ambos provedores
     */
    function selectSearchType(type) {
        // Atualizar campo hidden
        const searchTypeField = document.getElementById('searchType');
        if (searchTypeField) {
            searchTypeField.value = type;
        }

        // Resetar estilo dos cards (se existirem)
        const searchTypeResumed = document.getElementById('searchTypeResumed');
        if (searchTypeResumed) {
            searchTypeResumed.style.border = '2px solid transparent';
        }
        const searchTypeComplete = document.getElementById('searchTypeComplete');
        if (searchTypeComplete) {
            searchTypeComplete.style.border = '2px solid transparent';
        }

        // Marcar o radio correto (se existirem)
        const radioResumo = document.getElementById('radioResumo');
        if (radioResumo) {
            radioResumo.checked = (type === 'resumo');
        }
        const radioCompleto = document.getElementById('radioCompleto');
        if (radioCompleto) {
            radioCompleto.checked = (type === 'completo');
        }

        // Destacar o card selecionado (se existirem)
        if (type === 'resumo' && searchTypeResumed) {
            searchTypeResumed.style.border = '2px solid #17a2b8'; // cyan
            console.log('[AdvancedRoadmap] Tipo de busca: Resumida (válido para ambos provedores)');
        } else if (type === 'completo' && searchTypeComplete) {
            searchTypeComplete.style.border = '2px solid #ae3ec9'; // purple
            console.log('[AdvancedRoadmap] Tipo de busca: Completa (válido para ambos provedores)');
        }
    }

    /**
     * Verificar se há processamento de áudio em andamento
     */
    function isAudioProcessing() {
        const audioProcessingStatus = document.getElementById('audioProcessingStatus');
        return audioProcessingStatus && audioProcessingStatus.style.display !== 'none';
    }

    /**
     * Continuar com a opção selecionada
     */
    function continueWithOption() {
        // Verificar se há processamento de áudio
        if (isAudioProcessing()) {
            toastr.warning('Aguarde o processamento do áudio terminar antes de continuar');
            return;
        }

        let selectedOption = document.getElementById('selectedRoadmapOption').value;

        // Se não tiver opção selecionada mas estiver no modo manual com campo visível (v2),
        // automaticamente usar modo 'simple'
        if (!selectedOption) {
            const manualSubOptions = document.getElementById('manualSubOptions');
            const optionSimpleObservations = document.getElementById('optionSimpleObservations');

            // Se está no modo manual e não tem os cards de sub-opção (v2), usar 'simple'
            if (manualSubOptions && manualSubOptions.style.display !== 'none' && !optionSimpleObservations) {
                selectedOption = 'simple';
                document.getElementById('selectedRoadmapOption').value = 'simple';
            } else {
                toastr.error('Por favor, selecione uma opção antes de continuar');
                return;
            }
        }

        if (selectedOption === 'simple') {
            // Opção simples: criar roteiro direto com observações
            const observations = document.getElementById('simpleObservationsText').value.trim();

            if (!observations) {
                toastr.error('Por favor, adicione suas observações antes de continuar');
                return;
            }

            createSimpleRoadmap(observations);
        } else if (selectedOption === 'advanced') {
            // Opção avançada: gerar roteiro diretamente (sem perguntas)
            createAdvancedRoadmapDirect();
        }
    }

    /**
     * Criar roteiro no modo padrão (sem opções adicionais)
     */
    function createDefaultRoadmap() {
        // Verificar se há processamento de áudio
        if (isAudioProcessing()) {
            toastr.warning('Aguarde o processamento do áudio terminar antes de criar o roteiro');
            return;
        }

        const headlineId = document.getElementById('advancedRoadmapHeadlineId').value;
        const headlineText = document.getElementById('advancedRoadmapHeadline').value.trim();
        const aiProvider = document.getElementById('advancedRoadmapAI').value;

        // Validar se tem headline
        if (!headlineId && !headlineText) {
            toastr.error('Por favor, digite uma headline antes de continuar');
            return;
        }

        const saveToTable = document.getElementById('saveToTable').value;
        const advancedSearchEnabled = document.getElementById('advancedSearchEnabled').value;
        const enableReview = document.getElementById('enableRoadmapReview').checked ? '1' : '0';
        const searchProvider = document.getElementById('searchProvider').value;
        const searchType = document.getElementById('searchType').value;
        const viralVideoId = document.getElementById('selectedViralVideoId').value; // ✅ Vídeo selecionado da biblioteca

        // Preparar dados: enviar headline_id ou headline_text
        const requestData = {
            _token: window.AdvancedRoadmapModalConfig.csrfToken,
            ai_provider: aiProvider,
            mode: 'default',
            save_to: saveToTable,
            advanced_search: advancedSearchEnabled,
            enable_review: enableReview,
            search_provider: searchProvider,
            search_type: searchType,
            viral_video_id: viralVideoId || null // ✅ NOVO: Vídeo viral selecionado
        };

        // Se busca avançada estiver ativa, coletar resultados das buscas manuais
        if (advancedSearchEnabled === '1') {
            const manualSearchResults = collectAllManualSearchResults();

            if (manualSearchResults.queries && manualSearchResults.queries.length > 0) {
                // Adicionar dados de busca manual
                requestData.search_results_data = manualSearchResults;
                requestData.selected_links = manualSearchResults.selected_links || [];
                console.log('[AdvancedRoadmap] Resultados de busca manual coletados:', {
                    total_queries: manualSearchResults.queries.length,
                    total_selected_links: manualSearchResults.selected_links.length
                });
            } else {
                toastr.warning('Faça pelo menos uma busca antes de continuar');
                return;
            }
        }

        // Log para debug
        console.log('[AdvancedRoadmap] Criando roteiro com configurações:', {
            search_provider: searchProvider,
            search_type: searchType,
            advanced_search: advancedSearchEnabled,
            has_manual_search_results: advancedSearchEnabled === '1' && requestData.search_results_data ? true : false,
            viral_video_id: viralVideoId || 'Nenhum'
        });

        if (headlineId) {
            requestData.headline_id = headlineId;
        } else {
            requestData.headline_text = headlineText;
        }
        requestData.is_reprocess = document.getElementById('roadmapIsReprocess')?.value === '1' ? 1 : 0;

        // Criar roteiro diretamente (busca manual já foi feita pelo usuário)
        createRoadmapWithRequest(requestData, headlineId, saveToTable);
    }

    /**
     * Iniciar busca de links com tela de carregamento
     */
    function startLinksSearch(autoSearchDirection, headlineText) {
        // Resetar seleção
        selectedLinks = [];
        searchResultsData = null;

        // Mostrar tela de carregamento
        showState('loading_links');

        // Iniciar mensagens dinâmicas
        startLoadingMessages();

        // Obter URL da rota
        const listSearchUrl = window.AdvancedRoadmapRoutes?.listSearch
            || window.AdvancedRoadmapModalConfig?.routes?.listSearch
            || '/dashboard/user/headlines/suggested/advanced-roadmap/list-search';

        $.ajax({
            url: listSearchUrl,
            type: 'POST',
            data: {
                _token: window.AdvancedRoadmapModalConfig.csrfToken,
                autoSearchDirection: autoSearchDirection || '',
                headlineText: headlineText
            },
            success: function(response) {
                console.log('[AdvancedRoadmap] getListSearch response:', response);

                if (response.success && response.data && response.data.queries) {
                    searchResultsData = response.data;
                    stopLoadingMessages();
                    displayLinksSelection(response.data);
                } else {
                    stopLoadingMessages();
                    toastr.error('Erro ao buscar links. Tente novamente.');
                    showState('form');
                }
            },
            error: function(xhr, status, error) {
                console.error('[AdvancedRoadmap] getListSearch error:', error);
                stopLoadingMessages();
                toastr.error('Erro ao buscar links na internet');
                showState('form');
            }
        });
    }

    /**
     * Mensagens dinâmicas durante carregamento
     */
    let loadingMessagesInterval = null;
    const loadingMessages = [
        'Entendendo a busca necessária para seu roteiro...',
        'Preparando queries de pesquisa...',
        'Buscando informações relevantes...',
        'Extraindo links e informações...',
        'Organizando resultados por categoria...',
        'Quase pronto!'
    ];
    let currentMessageIndex = 0;

    function startLoadingMessages() {
        currentMessageIndex = 0;
        const messageElement = document.getElementById('loadingLinksMessage');
        const progressBar = document.getElementById('loadingLinksProgressBar');

        if (!messageElement) return;

        // Atualizar mensagem inicial
        messageElement.textContent = loadingMessages[0];
        progressBar.style.width = '10%';

        loadingMessagesInterval = setInterval(() => {
            currentMessageIndex++;
            if (currentMessageIndex < loadingMessages.length) {
                messageElement.textContent = loadingMessages[currentMessageIndex];
                // Atualizar progresso (10% a 90%)
                const progress = 10 + (currentMessageIndex * (80 / (loadingMessages.length - 1)));
                progressBar.style.width = progress + '%';
            }
        }, 2000); // Trocar mensagem a cada 2 segundos
    }

    function stopLoadingMessages() {
        if (loadingMessagesInterval) {
            clearInterval(loadingMessagesInterval);
            loadingMessagesInterval = null;
        }
        const progressBar = document.getElementById('loadingLinksProgressBar');
        if (progressBar) {
            progressBar.style.width = '100%';
        }
    }

    /**
     * Exibir tela de seleção de links
     */
    function displayLinksSelection(data) {
        console.log('[AdvancedRoadmap] displayLinksSelection - data recebida:', data);

        // A estrutura é: data.queries (array diretamente)
        if (!data || !data.queries || !Array.isArray(data.queries)) {
            console.error('[AdvancedRoadmap] Estrutura de dados inválida:', data);
            toastr.error('Nenhum resultado encontrado');
            showState('form');
            return;
        }

        const container = document.getElementById('linksContainer');
        if (!container) {
            console.error('[AdvancedRoadmap] Container linksContainer não encontrado');
            return;
        }

        container.innerHTML = '';
        selectedLinks = [];

        // Iterar sobre cada query (data.queries já é o array)
        console.log('[AdvancedRoadmap] Total de queries:', data.queries.length);

        data.queries.forEach((queryItem, queryIndex) => {
            const itemPt = queryItem.item_pt || `Item ${queryItem.posicao}`;
            const results = queryItem.result || [];
            const idioma = queryItem.idioma || '';
            const needsTranslation = idioma !== 'pt' && idioma !== 'br';

            console.log(`[AdvancedRoadmap] Query ${queryIndex + 1}: ${itemPt} - ${results.length} resultados`);

            // Mostrar TODOS os resultados (sem limite)
            if (results.length === 0) {
                console.log(`[AdvancedRoadmap] Query ${queryIndex + 1} não tem resultados, pulando...`);
                return;
            }

            console.log(`[AdvancedRoadmap] Query ${queryIndex + 1} será exibida com ${results.length} links`);

            // Criar card para este item
            const itemCard = document.createElement('div');
            itemCard.className = 'card mb-3 border-purple';
            itemCard.innerHTML = `
                <div class="d-flex card-header bg-purple-lt">
                    <div class="d-flex w-full flex-column">
                        <div class="row mb-2">
                            <div class="col-6">
                                <h6 class="mb-0 fw-bold d-flex align-items-center">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon me-2">
                                        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                                        <circle cx="12" cy="10" r="3"></circle>
                                    </svg>
                                    ${itemPt}
                                </h6>
                            </div>
                            <div class="col-6 text-end d-flex align-items-center justify-content-end gap-2">
                                ${queryItem.descricao ? `<small class="text-muted">${queryItem.descricao}</small>` : ''}
                                ${needsTranslation ? `
                                    <button type="button"
                                        class="btn btn-sm btn-primary translate-all-btn"
                                        id="translate_all_${queryIndex}"
                                        data-query-index="${queryIndex}"
                                        onclick="event.stopPropagation(); AdvancedRoadmapModal.translateAllResults(${queryIndex});"
                                        title="Traduzir todos os resultados para português">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon me-1">
                                            <path d="M5 8l6 6"></path>
                                            <path d="M4 14l6-6 2-3"></path>
                                            <path d="M2 5h12"></path>
                                            <path d="M7 2h1v6H7z"></path>
                                            <path d="M22 22l-5-10-5 10"></path>
                                            <path d="M14 18h6"></path>
                                        </svg>
                                        Traduzir
                                    </button>
                                ` : ''}
                            </div>
                        </div>
                        <div class="row text-end align-items-center justify-content-center">
                            <div class="col-12 align-items-center justify-content-center">
                                <div class="d-flex gap-2">
                                    <span class="badge bg-purple text-white">${results.length} ${results.length === 1 ? 'link encontrado' : 'links encontrados'}</span>
                                    <span class="badge bg-info text-white" id="selectedCount_${queryIndex}">0/${MAX_SELECTED_LINKS_PER_CATEGORY} selecionados</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="card-body" style="max-height: 400px; overflow-y: auto;">
                    <div class="list-group list-group-flush">
                        ${results.map((result, resultIndex) => {
                            const linkId = `link_${queryIndex}_${resultIndex}`;
                            const titleId = `title_${queryIndex}_${resultIndex}`;
                            const snippetId = `snippet_${queryIndex}_${resultIndex}`;
                            return `
                                <div class="list-group-item px-0">
                                    <div class="form-check">
                                        <input class="form-check-input link-checkbox" type="checkbox"
                                            id="${linkId}"
                                            data-link-url="${result.link || ''}"
                                            data-link-title="${(result.title || '').replace(/"/g, '&quot;')}"
                                            data-link-snippet="${(result.snippet || '').replace(/"/g, '&quot;')}"
                                            data-query-posicao="${queryItem.posicao}"
                                            data-query-item-pt="${queryItem.item_pt || ''}"
                                            data-query-index="${queryIndex}">
                                        <label class="form-check-label w-100" for="${linkId}">
                                            <div class="d-flex justify-content-between align-items-start">
                                                <div class="flex-fill">
                                                    <a href="${result.link || '#'}" target="_blank"
                                                        class="text-decoration-none fw-bold text-primary"
                                                        onclick="event.stopPropagation()"
                                                        id="${titleId}">
                                                        ${result.title || 'Sem título'}
                                                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon ms-1">
                                                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                                                            <polyline points="15 3 21 3 21 9"></polyline>
                                                            <line x1="10" y1="14" x2="21" y2="3"></line>
                                                        </svg>
                                                    </a>
                                                    ${result.snippet ? `<p class="text-muted small mb-0 mt-1" id="${snippetId}">${result.snippet.substring(0, 150)}${result.snippet.length > 150 ? '...' : ''}</p>` : ''}
                                                </div>
                                            </div>
                                        </label>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            `;

            container.appendChild(itemCard);
        });

        // Adicionar event listeners aos checkboxes
        document.querySelectorAll('.link-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', updateSelectedLinks);
        });

        // Atualizar contador (inicializar vazio)
        updateSelectedLinksCount({});

        // Adicionar listeners aos botões
        const backBtn = document.getElementById('backToFormFromLinksBtn');
        const continueBtn = document.getElementById('continueWithSelectedLinksBtn');

        if (backBtn) {
            backBtn.onclick = () => {
                // Limpar seleção
                selectedLinks = [];
                searchResultsData = null;

                // Limpar container de links
                const linksContainer = document.getElementById('linksContainer');
                if (linksContainer) {
                    linksContainer.innerHTML = '';
                }

                // Desmarcar todos os checkboxes
                document.querySelectorAll('.link-checkbox').forEach(checkbox => {
                    checkbox.checked = false;
                    checkbox.disabled = false;
                });

                // Limpar dados temporários de request
                if (window.pendingRoadmapRequest) {
                    delete window.pendingRoadmapRequest;
                }

                // Voltar para o formulário
                showState('form');
            };
        }

        if (continueBtn) {
            // Habilitar botão (permitir continuar mesmo sem links selecionados)
            continueBtn.disabled = false;
            continueBtn.onclick = () => {
                continueWithSelectedLinks();
            };
        }

        // Mostrar tela de seleção
        showState('select_links');
    }

    /**
     * Atualizar contagem de links selecionados
     */
    function updateSelectedLinks() {
        selectedLinks = [];

        // Agrupar por categoria (query_index)
        const linksByCategory = {};

        document.querySelectorAll('.link-checkbox:checked').forEach(checkbox => {
            const queryIndex = checkbox.dataset.queryIndex;
            if (!linksByCategory[queryIndex]) {
                linksByCategory[queryIndex] = [];
            }
            linksByCategory[queryIndex].push({
                url: checkbox.dataset.linkUrl,
                title: checkbox.dataset.linkTitle,
                snippet: checkbox.dataset.linkSnippet,
                query_posicao: checkbox.dataset.queryPosicao,
                query_item_pt: checkbox.dataset.queryItemPt
            });
        });

        // Adicionar todos os links selecionados ao array
        Object.values(linksByCategory).forEach(categoryLinks => {
            selectedLinks.push(...categoryLinks);
        });

        updateSelectedLinksCount(linksByCategory);
    }

    /**
     * Atualizar UI do contador
     */
    function updateSelectedLinksCount(linksByCategory = {}) {
        const continueBtn = document.getElementById('continueWithSelectedLinksBtn');
        const maxCountElement = document.getElementById('maxLinksCount');

        // Atualizar contador total
        const totalSelected = selectedLinks.length;
        const totalCategories = Object.keys(linksByCategory).length;

        // Agrupar checkboxes por categoria para atualizar contadores
        const checkboxesByCategory = {};
        document.querySelectorAll('.link-checkbox').forEach(checkbox => {
            const queryIndex = checkbox.dataset.queryIndex;
            if (!checkboxesByCategory[queryIndex]) {
                checkboxesByCategory[queryIndex] = [];
            }
            checkboxesByCategory[queryIndex].push(checkbox);
        });

        // Atualizar contadores por categoria
        Object.keys(checkboxesByCategory).forEach(queryIndex => {
            const categorySelected = linksByCategory[queryIndex] ? linksByCategory[queryIndex].length : 0;
            const categoryCountElement = document.getElementById(`selectedCount_${queryIndex}`);

            if (categoryCountElement) {
                categoryCountElement.textContent = `${categorySelected}/${MAX_SELECTED_LINKS_PER_CATEGORY} selecionados`;

                if (categorySelected >= MAX_SELECTED_LINKS_PER_CATEGORY) {
                    categoryCountElement.className = 'badge bg-success ms-2 text-white';
                } else if (categorySelected > 0) {
                    categoryCountElement.className = 'badge bg-info ms-2 text-white';
                } else {
                    categoryCountElement.className = 'badge bg-secondary ms-2 text-white';
                }
            }

            // Desabilitar/habilitar checkboxes da categoria baseado no limite
            checkboxesByCategory[queryIndex].forEach(checkbox => {
                checkbox.disabled = categorySelected >= MAX_SELECTED_LINKS_PER_CATEGORY && !checkbox.checked;
            });
        });

        // Atualizar contador geral (se existir)
        const countElement = document.getElementById('selectedLinksCount');
        if (countElement) {
            countElement.textContent = `${totalSelected} selecionados`;

            if (totalSelected > 0) {
                countElement.className = 'badge bg-purple text-white';
            } else {
                countElement.className = 'badge bg-secondary text-white';
            }
        }

        if (maxCountElement) {
            maxCountElement.textContent = MAX_SELECTED_LINKS_PER_CATEGORY;
        }

        // Permitir continuar mesmo sem links selecionados (usuário pode escolher)
        if (continueBtn) {
            continueBtn.disabled = false;
        }
    }

    /**
     * Continuar criação do roteiro com links selecionados
     */
    function continueWithSelectedLinks() {
        // Permitir continuar mesmo sem links selecionados (usuário pode escolher)

        // Adicionar dados de busca e links selecionados ao request
        if (window.pendingRoadmapRequest) {
            // Adicionar retorno completo de list-search
            if (searchResultsData) {
                window.pendingRoadmapRequest.search_results_data = searchResultsData;
            }

            // Adicionar links selecionados (pode ser array vazio se usuário não selecionou nenhum)
            window.pendingRoadmapRequest.selected_links = selectedLinks || [];
            window.pendingRoadmapRequest.is_reprocess = document.getElementById('roadmapIsReprocess')?.value === '1' ? 1 : 0;

            // Obter dados salvos
            const headlineId = window.pendingRoadmapRequest.headline_id || null;
            const saveToTable = window.pendingRoadmapRequest.save_to || 'eng_reversa_headlines';

            // Criar roteiro
            createRoadmapWithRequest(window.pendingRoadmapRequest, headlineId, saveToTable);

            // Limpar dados temporários
            delete window.pendingRoadmapRequest;
        } else {
            toastr.error('Erro: dados do roteiro não encontrados');
            showState('form');
        }
    }

    /**
     * Criar roteiro com request preparado
     */
    function createRoadmapWithRequest(requestData, headlineId, saveToTable) {
        // Mostrar estado de criação
        showState('creating');

        // AJAX para criar roteiro padrão
        $.ajax({
            url: window.AdvancedRoadmapModalConfig.routes.store,
            type: 'POST',
            data: requestData,
            success: function(data) {
                if(data.success) {
                    // Determinar ID para polling baseado em save_to
                    let pollingId;
                    if (saveToTable === 'user_roadmaps') {
                        // Para user_roadmaps: priorizar headline_id (favorites), depois roadmap_id (roadmaps/index)
                        pollingId = data.headline_id || data.roadmap_id || headlineId;
                    } else {
                        // Para eng_reversa_headlines (suggested), usar headline_id
                        pollingId = data.headline_id || data.roadmap_id || headlineId;
                    }

                    if (pollingId) {
                        startLongPolling(pollingId);
                    } else {
                        // Se não tem ID, mostrar mensagem que roteiro está sendo processado
                        toastr.success('Roteiro avançado enviado para processamento! Aguarde a conclusão.');
                    }
                    toastr.success('Roteiro avançado enviado para processamento!');
                } else {
                    // Voltar para o formulário em caso de erro
                    showState('form');
                    toastr.error(data.message || 'Erro ao criar o roteiro avançado');
                }
            },
            error: function(xhr) {
                // Voltar para o formulário em caso de erro
                showState('form');
                toastr.error('Erro ao criar o roteiro avançado');
                console.error(xhr);
            }
        });
    }

    /**
     * Criar roteiro no modo simples
     */
    function createSimpleRoadmap(observations) {
        const headlineId = document.getElementById('advancedRoadmapHeadlineId').value;
        const headlineText = document.getElementById('advancedRoadmapHeadline').value.trim();
        const aiProvider = document.getElementById('advancedRoadmapAI').value;

        // Validar se tem headline
        if (!headlineId && !headlineText) {
            toastr.error('Por favor, digite uma headline antes de continuar');
            return;
        }

        const saveToTable = document.getElementById('saveToTable').value;
        const advancedSearchEnabled = document.getElementById('advancedSearchEnabled').value;
        const enableReview = document.getElementById('enableRoadmapReview').checked ? '1' : '0';
        const searchProvider = document.getElementById('searchProvider').value;
        const searchType = document.getElementById('searchType').value;
        const viralVideoId = document.getElementById('selectedViralVideoId').value; // ✅ Vídeo selecionado da biblioteca

        // Preparar dados: enviar headline_id ou headline_text
        const requestData = {
            _token: window.AdvancedRoadmapModalConfig.csrfToken,
            observations: observations,
            ai_provider: aiProvider,
            mode: 'simple',
            save_to: saveToTable,
            advanced_search: advancedSearchEnabled,
            enable_review: enableReview,
            search_provider: searchProvider,
            search_type: searchType,
            viral_video_id: viralVideoId || null // ✅ NOVO: Vídeo viral selecionado
        };

        if (headlineId) {
            requestData.headline_id = headlineId;
        } else {
            requestData.headline_text = headlineText;
        }
        requestData.is_reprocess = document.getElementById('roadmapIsReprocess')?.value === '1' ? 1 : 0;

        // Log para debug
        console.log('[AdvancedRoadmap] Criando roteiro simples:', {
            has_observations: !!observations,
            observations_length: observations.length,
            viral_video_id: viralVideoId || 'Nenhum (busca automática)',
            search_provider: searchProvider,
            search_type: searchType
        });

        // Mostrar estado de criação
        showState('creating');

        // AJAX para criar roteiro com observações simples
        $.ajax({
            url: window.AdvancedRoadmapModalConfig.routes.store,
            type: 'POST',
            data: requestData,
            success: function(data) {
                if(data.success) {
                    // Determinar ID para polling baseado em save_to
                    let pollingId;
                    if (saveToTable === 'user_roadmaps') {
                        // Para user_roadmaps: priorizar headline_id (favorites), depois roadmap_id (roadmaps/index)
                        pollingId = data.headline_id || data.roadmap_id || headlineId;
                    } else {
                        // Para eng_reversa_headlines (suggested), usar headline_id
                        pollingId = data.headline_id || data.roadmap_id || headlineId;
                    }

                    if (pollingId) {
                        startLongPolling(pollingId);
                    } else {
                        toastr.success('Roteiro avançado enviado para processamento! Aguarde a conclusão.');
                    }
                    toastr.success('Roteiro avançado enviado para processamento!');
                } else {
                    // Voltar para o formulário em caso de erro
                    showState('form');
                    toastr.error(data.message || 'Erro ao criar o roteiro avançado');
                }
            },
            error: function(xhr) {
                // Voltar para o formulário em caso de erro
                showState('form');
                toastr.error('Erro ao criar o roteiro avançado');
                console.error(xhr);
            }
        });
    }

    /**
     * Criar roteiro avançado diretamente (sem perguntas)
     */
    function createAdvancedRoadmapDirect() {
        // Verificar se há processamento de áudio
        if (isAudioProcessing()) {
            toastr.warning('Aguarde o processamento do áudio terminar antes de criar o roteiro');
            return;
        }

        const headlineId = document.getElementById('advancedRoadmapHeadlineId').value;
        const headlineText = document.getElementById('advancedRoadmapHeadline').value.trim();
        const aiProvider = document.getElementById('advancedRoadmapAI').value;

        // Validar se tem headline
        if (!headlineId && !headlineText) {
            toastr.error('Por favor, digite uma headline antes de continuar');
            return;
        }

        // Capturar cérebros selecionados
        const brainSelect = document.getElementById('select-brain-ids');
        let brainIds = [];

        if (brainSelect) {
            // Verificar se é TomSelect
            if (brainSelect.tomselect) {
                brainIds = brainSelect.tomselect.getValue() || [];
            } else {
                // Fallback para select nativo
                const selectedOptions = Array.from(brainSelect.selectedOptions);
                brainIds = selectedOptions.map(option => option.value).filter(val => val);
            }
        }

        const saveToTable = document.getElementById('saveToTable').value;
        const advancedSearchEnabled = document.getElementById('advancedSearchEnabled').value;
        const enableReview = document.getElementById('enableRoadmapReview').checked ? '1' : '0';
        const searchProvider = document.getElementById('searchProvider').value;
        const searchType = document.getElementById('searchType').value;
        const viralVideoId = document.getElementById('selectedViralVideoId').value;

        // Capturar observações do campo de informações adicionais
        const observationsElement = document.getElementById('simpleObservationsText');
        const observations = observationsElement ? observationsElement.value.trim() : '';

        console.log('[AdvancedRoadmap] Campo de observações:', {
            element_exists: !!observationsElement,
            value: observations,
            value_length: observations.length
        });

        // Preparar dados: enviar headline_id ou headline_text
        const requestData = {
            _token: window.AdvancedRoadmapModalConfig.csrfToken,
            ai_provider: aiProvider,
            mode: 'default',
            save_to: saveToTable,
            advanced_search: advancedSearchEnabled,
            enable_review: enableReview,
            search_provider: searchProvider,
            search_type: searchType,
            viral_video_id: viralVideoId || null
        };

        // Adicionar brain_ids se houver cérebros selecionados
        if (brainIds.length > 0) {
            requestData.brain = brainIds;
            console.log('[AdvancedRoadmap] Cérebros selecionados:', brainIds);
        }

        // Sempre adicionar observações (mesmo que vazio, para garantir que o campo seja enviado)
        requestData.observations = observations || '';

        // Se busca avançada estiver ativa e houver direcionamento, adicionar às observações
        const autoSearchDirection = document.getElementById('autoSearchDirectionText').value.trim();
        if (advancedSearchEnabled === '1' && autoSearchDirection) {
            requestData.observations = (requestData.observations ? requestData.observations + '\n\n' : '') + autoSearchDirection;
            console.log('[AdvancedRoadmap] Direcionamento de busca adicionado:', autoSearchDirection);
        }

        console.log('[AdvancedRoadmap] Observações finais no payload:', {
            observations: requestData.observations,
            observations_length: requestData.observations.length
        });

        if (headlineId) {
            requestData.headline_id = headlineId;
        } else {
            requestData.headline_text = headlineText;
        }
        requestData.is_reprocess = document.getElementById('roadmapIsReprocess')?.value === '1' ? 1 : 0;

        // Log completo do payload para debug
        console.log('[AdvancedRoadmap] Payload completo antes de enviar:', {
            headline_id: requestData.headline_id || null,
            headline_text: requestData.headline_text || null,
            observations: requestData.observations,
            observations_length: requestData.observations ? requestData.observations.length : 0,
            has_brain_ids: brainIds.length > 0,
            brain_ids: brainIds,
            brain: requestData.brain || null,
            mode: requestData.mode,
            search_provider: searchProvider,
            search_type: searchType,
            advanced_search: advancedSearchEnabled,
            viral_video_id: viralVideoId || 'Nenhum (busca automática)',
            full_payload: requestData
        });

        // Mostrar estado de criação
        showState('creating');

        // Log final do payload que será enviado
        console.log('[AdvancedRoadmap] Enviando payload final:', JSON.stringify(requestData, null, 2));

        // AJAX para criar roteiro avançado
        $.ajax({
            url: window.AdvancedRoadmapModalConfig.routes.store,
            type: 'POST',
            data: requestData,
            success: function(data) {
                if(data.success) {
                    // Determinar ID para polling baseado em save_to
                    let pollingId;
                    if (saveToTable === 'user_roadmaps') {
                        // Para user_roadmaps: priorizar headline_id (favorites), depois roadmap_id (roadmaps/index)
                        pollingId = data.headline_id || data.roadmap_id || headlineId;
                    } else {
                        // Para eng_reversa_headlines (suggested), usar headline_id
                        pollingId = data.headline_id || data.roadmap_id || headlineId;
                    }

                    if (pollingId) {
                        startLongPolling(pollingId);
                    } else {
                        toastr.success('Roteiro avançado enviado para processamento! Aguarde a conclusão.');
                    }
                    toastr.success('Roteiro avançado enviado para processamento!');
                } else {
                    // Voltar para o formulário em caso de erro
                    showState('form');
                    toastr.error(data.message || 'Erro ao criar o roteiro avançado');
                }
            },
            error: function(xhr) {
                // Voltar para o formulário em caso de erro
                showState('form');
                toastr.error('Erro ao criar o roteiro avançado');
                console.error(xhr);
            }
        });
    }

    /**
     * Gerar perguntas estratégicas
     */
    function generateQuestions() {
        const headlineId = document.getElementById('advancedRoadmapHeadlineId').value;
        const headlineText = document.getElementById('advancedRoadmapHeadline').value.trim();

        // Validar se tem headline
        if (!headlineId && !headlineText) {
            toastr.error('Por favor, digite uma headline antes de continuar');
            return;
        }

        const saveToTable = document.getElementById('saveToTable').value;

        // Preparar dados: enviar headline_id ou headline_text
        const requestData = {
            _token: window.AdvancedRoadmapModalConfig.csrfToken,
            save_to: saveToTable
        };

        if (headlineId) {
            requestData.headline_id = headlineId;
        } else {
            requestData.headline_text = headlineText;
        }

        // Mostrar estado de gerando perguntas
        showState('generating_questions');

        // AJAX para gerar perguntas
        $.ajax({
            url: window.AdvancedRoadmapModalConfig.routes.generateQuestions,
            type: 'POST',
            data: requestData,
            success: function(data) {
                if(data.success && data.questions && data.questions.length > 0) {
                    generatedQuestions = data.questions;
                    renderQuestions(data.questions);
                    document.getElementById('advancedRoadmapHeadlineQuestions').value = document.getElementById('advancedRoadmapHeadline').value;
                    showState('questions');
                    toastr.success('Perguntas geradas! Responda para personalizar seu roteiro.');
                } else {
                    showState('form');
                    toastr.error(data.message || 'Erro ao gerar perguntas');
                }
            },
            error: function(xhr) {
                showState('form');
                toastr.error('Erro ao gerar perguntas. Tente novamente.');
                console.error(xhr);
            }
        });
    }

    /**
     * Renderizar perguntas na tela
     */
    function renderQuestions(questions) {
        const container = document.getElementById('questionsContainer');
        container.innerHTML = '';

        questions.forEach((question, index) => {
            const questionDiv = document.createElement('div');
            questionDiv.className = 'mb-4';
            questionDiv.innerHTML = `
                <label class="form-label fw-bold">
                    <span class="badge bg-purple me-2 text-white">${index + 1}</span>
                    ${question}
                </label>
                <textarea class="form-control question-answer" data-index="${index}" rows="3" placeholder="Digite sua resposta aqui..."></textarea>
            `;
            container.appendChild(questionDiv);
        });
    }

    /**
     * Salvar roteiro avançado (com perguntas respondidas)
     */
    function saveRoadmap() {
        const headlineId = document.getElementById('advancedRoadmapHeadlineId').value;
        const headlineText = document.getElementById('advancedRoadmapHeadline').value.trim();
        const aiProvider = document.getElementById('advancedRoadmapAI').value;

        // Validar se tem headline
        if (!headlineId && !headlineText) {
            toastr.error('Por favor, digite uma headline antes de continuar');
            return;
        }

        // Coletar respostas
        const answerElements = document.querySelectorAll('.question-answer');
        const answers = Array.from(answerElements).map(el => el.value.trim());

        // Validar se todas as perguntas foram respondidas
        if (answers.some(answer => !answer)) {
            toastr.error('Por favor, responda todas as perguntas antes de continuar');
            return;
        }

        const saveToTable = document.getElementById('saveToTable').value;
        const advancedSearchEnabled = document.getElementById('advancedSearchEnabled').value;
        const enableReview = document.getElementById('enableRoadmapReview').checked ? '1' : '0';
        const searchProvider = document.getElementById('searchProvider').value;
        const searchType = document.getElementById('searchType').value;
        const viralVideoId = document.getElementById('selectedViralVideoId').value; // ✅ Vídeo selecionado da biblioteca
        const seachesSelected = document.getElementById('seachesSelected').value; // ✅ Vídeo selecionado da biblioteca

        // Preparar dados: enviar headline_id ou headline_text
        const requestData = {
            _token: window.AdvancedRoadmapModalConfig.csrfToken,
            questions: generatedQuestions,
            answers: answers,
            ai_provider: aiProvider,
            save_to: saveToTable,
            advanced_search: advancedSearchEnabled,
            enable_review: enableReview,
            search_provider: searchProvider,
            search_type: searchType,
            viral_video_id: viralVideoId || null
        };

        if (headlineId) {
            requestData.headline_id = headlineId;
        } else {
            requestData.headline_text = headlineText;
        }
        requestData.is_reprocess = document.getElementById('roadmapIsReprocess')?.value === '1' ? 1 : 0;

        // Mostrar estado de criação
        showState('creating');

        // AJAX para criar roteiro avançado
        $.ajax({
            url: window.AdvancedRoadmapModalConfig.routes.store,
            type: 'POST',
            data: requestData,
            success: function(data) {
                if(data.success) {
                    // Determinar ID para polling baseado em save_to
                    let pollingId;
                    if (saveToTable === 'user_roadmaps') {
                        // Para user_roadmaps: priorizar headline_id (favorites), depois roadmap_id (roadmaps/index)
                        pollingId = data.headline_id || data.roadmap_id || headlineId;
                    } else {
                        // Para eng_reversa_headlines (suggested), usar headline_id
                        pollingId = data.headline_id || data.roadmap_id || headlineId;
                    }

                    if (pollingId) {
                        startLongPolling(pollingId);
                    } else {
                        toastr.success('Roteiro avançado enviado para processamento! Aguarde a conclusão.');
                    }
                    toastr.success('Roteiro avançado enviado para processamento!');
                } else {
                    // Voltar para as perguntas em caso de erro
                    showState('questions');
                    toastr.error(data.message || 'Erro ao criar o roteiro avançado');
                }
            },
            error: function(xhr) {
                // Voltar para as perguntas em caso de erro
                showState('questions');
                toastr.error('Erro ao criar o roteiro avançado');
                console.error(xhr);
            }
        });
    }

    /**
     * Controlar estados do modal
     */
    // Variáveis para armazenar dados de busca
    let searchResultsData = null;
    let selectedLinks = [];

    function showState(state) {
        // Esconder todos os estados (verificando se existem antes)
        const states = [
            'advancedRoadmapCreatingState',
            'advancedRoadmapFormState',
            'advancedRoadmapGeneratingQuestionsState',
            'advancedRoadmapQuestionsState',
            'advancedRoadmapCreatedState',
            'advancedRoadmapLoadingLinksState',
            'advancedRoadmapSelectLinksState'
        ];

        states.forEach(stateId => {
            const element = document.getElementById(stateId);
            if (element) {
                element.style.display = 'none';
            }
        });

        // Esconder botões (verificando se existem antes)
        const buttons = [
            'createDefaultRoadmapBtn',
            'continueOptionBtn',
            'generateQuestionsBtn',
            'createAdvancedRoadmapBtn'
        ];

        buttons.forEach(buttonId => {
            const button = document.getElementById(buttonId);
            if (button) {
                button.style.display = 'none';
            }
        });

        // Mostrar o estado solicitado
        if (state !== 'creating' && state !== 'loading_links') {
            hideArticleSearchMessage();
        }

        switch(state) {
            case 'form':
                const formState = document.getElementById('advancedRoadmapFormState');
                if (formState) formState.style.display = 'block';
                stopInitialProgressAnimation();
                // NÃO mostrar botão por padrão - usuário deve escolher uma opção principal primeiro
                // O botão aparecerá quando selecionar Manual (sub-opções) ou Automático (busca)
                break;
            case 'generating_questions':
                const generatingState = document.getElementById('advancedRoadmapGeneratingQuestionsState');
                if (generatingState) generatingState.style.display = 'block';
                break;
            case 'questions':
                const questionsState = document.getElementById('advancedRoadmapQuestionsState');
                if (questionsState) questionsState.style.display = 'block';
                const createBtn = document.getElementById('createAdvancedRoadmapBtn');
                if (createBtn) createBtn.style.display = 'inline-block';
                break;
            case 'loading_links':
                const loadingLinksState = document.getElementById('advancedRoadmapLoadingLinksState');
                if (loadingLinksState) loadingLinksState.style.display = 'block';
                // Esconder botão voltar do footer quando estiver carregando links
                const backToMainOptionsBtnLoading = document.getElementById('backToMainOptionsBtn');
                if (backToMainOptionsBtnLoading) {
                    backToMainOptionsBtnLoading.style.display = 'none';
                }
                break;
            case 'select_links':
                const selectLinksState = document.getElementById('advancedRoadmapSelectLinksState');
                if (selectLinksState) selectLinksState.style.display = 'block';
                // Esconder botão voltar do footer quando estiver na tela de seleção de links
                // O botão voltar dentro da tela de links (backToFormFromLinksBtn) já está configurado
                const backToMainOptionsBtnSelect = document.getElementById('backToMainOptionsBtn');
                if (backToMainOptionsBtnSelect) {
                    backToMainOptionsBtnSelect.style.display = 'none';
                }
                break;
            case 'creating':
                const creatingState = document.getElementById('advancedRoadmapCreatingState');
                if (creatingState) creatingState.style.display = 'block';
                hideArticleSearchMessage();
                // Iniciar animação progressiva inicial
                startInitialProgressAnimation();
                break;
            case 'result':
                const resultState = document.getElementById('advancedRoadmapCreatedState');
                if (resultState) resultState.style.display = 'block';
                stopInitialProgressAnimation();
                break;
        }

        const footerEl = document.getElementById('advancedRoadmapModalFooter');
        if (footerEl) {
            footerEl.style.display = (state === 'result' || state === 'creating' || state === 'loading_links') ? 'none' : '';
        }
    }

    /**
     * Iniciar long polling para verificar status
     */
    function startLongPolling(headlineId) {
        let pollCount = 0;
        const maxPolls = 120; // Máximo 10 minutos (120 * 5 segundos) - aumentado para suportar busca + criação + revisão
        isPollingActive = true;
        articleProgressShown = false;
        hideArticleSearchMessage();

        // Parar animação inicial quando polling começar (mantém o progresso atual)
        stopInitialProgressAnimation();

        function pollStatus() {
            if (!isPollingActive) {
                return;
            }
            pollCount++;
            updateProgress(pollCount, maxPolls);

            $.ajax({
                url: window.AdvancedRoadmapModalConfig.routes.show.replace('__ID__', headlineId),
                type: 'GET',
                data: {
                    headline_id: headlineId
                },
                success: function(data) {
                    console.log('[AdvancedRoadmap] Polling status:', data);

                    if (Boolean(data.use_article) && !articleProgressShown) {
                        let message = data.article_message;
                        if (!message) {
                            if (data.use_article_niche) {
                                message = 'Buscando artigos específicos sobre ' + data.use_article_niche + '...';
                            } else {
                                message = 'Buscando artigos científicos confiáveis...';
                            }
                        }
                        setProgressMessage(message, 25, false);
                        showArticleSearchMessage(message);
                        articleProgressShown = true;
                    }

                    if(data.success && data.roadmap_advanced && data.status === 'completed') {
                        // Roteiro concluído com sucesso
                        console.log('[AdvancedRoadmap] Roteiro concluído! Mostrando resultado');
                        document.getElementById('advancedRoadmapHeadlineResult').value = document.getElementById('advancedRoadmapHeadline').value;
                        document.getElementById('advancedRoadmapResult').value = data.roadmap_advanced;
                        document.getElementById('advancedRoadmapHeadlineId').value = headlineId || '';
                        const chatResourceId = data.roadmap_id || data.headline_id || headlineId || '';
                        document.getElementById('advancedRoadmapChatResourceId').value = chatResourceId;
                        const saveToField = document.getElementById('saveToTable');
                        const idForUpdateEl = document.getElementById('advancedRoadmapIdForUpdate');
                        var updateId = data.roadmap_id || '';
                        if (!updateId && saveToField && saveToField.value === 'user_roadmaps' && (headlineId || chatResourceId)) {
                            updateId = headlineId || chatResourceId;
                        }
                        if (idForUpdateEl) idForUpdateEl.value = updateId;
                        const resourceTypeField = document.getElementById('advancedRoadmapChatResourceType');
                        if (resourceTypeField) {
                            resourceTypeField.value = data.roadmap_source || (saveToField && saveToField.value) || resourceTypeField.value || 'eng_reversa_headlines';
                        }

                        // Verificar se há search_text para mostrar a aba de fontes
                        if(data.search_text && data.search_text.trim() !== '') {
                            console.log('[AdvancedRoadmap] Dados de pesquisa encontrados');
                            // Mostrar a aba de fontes
                            document.getElementById('sources-tab-li').style.display = 'block';

                            // Formatar e exibir o search_text
                            let searchTextFormatted = data.search_text.replace(/\n/g, '<br>');
                            document.getElementById('advancedSearchSourcesContent').innerHTML = searchTextFormatted;
                        } else {
                            // Esconder a aba de fontes se não houver dados
                            document.getElementById('sources-tab-li').style.display = 'none';
                            document.getElementById('advancedSearchSourcesContent').innerHTML = '';
                        }

                        showState('result');
                        toastr.success('Roteiro avançado criado com sucesso!');
                        stopPolling();
                    } else if(data.success === false || data.status !== 'completed') {
                        console.log('[AdvancedRoadmap] Roteiro ainda processando...', {
                            pollCount: pollCount,
                            status: data.status
                        });

                        // Roteiro ainda está sendo processado - continuar polling
                        if(pollCount >= maxPolls) {
                            showState('form');
                            toastr.error('Timeout: O roteiro está demorando mais que o esperado. Tente novamente.');
                            stopPolling();
                        } else {
                            pollingTimeout = setTimeout(pollStatus, 5000);
                        }
                    } else if(pollCount >= maxPolls) {
                        showState('form');
                        toastr.error('Timeout: O roteiro está demorando mais que o esperado. Tente novamente.');
                        stopPolling();
                    } else {
                        pollingTimeout = setTimeout(pollStatus, 5000);
                    }
                },
                error: function(xhr) {
                    if(pollCount >= maxPolls) {
                        isPollingActive = false;
                        showState('form');
                        toastr.error('Erro ao verificar status do roteiro');
                    } else {
                        pollingTimeout = setTimeout(pollStatus, 5000);
                    }
                }
            });
        }
        pollingTimeout = setTimeout(pollStatus, 2000);
    }

    /**
     * Atualizar barra de progresso
     */
    function updateProgress(current, max) {
        // Calcular progresso base (18% a 100%)
        // Começar de 18% (onde a animação inicial parou) e ir até 100%
        const minProgress = 18;
        const maxProgress = 100;
        const range = maxProgress - minProgress;
        const basePercentage = Math.min((current / max) * 100, 100);
        const adjustedPercentage = minProgress + (basePercentage / 100) * range;
        const percentage = articleProgressShown ? Math.max(adjustedPercentage, 25) : adjustedPercentage;

        document.querySelector('#advancedProgressBar').style.width = percentage + '%';
        document.querySelector('#advancedProgressBar').setAttribute('aria-valuenow', percentage);

        let statusText = '';
        if (current <= 6) {
            statusText = 'Iniciando processamento...';
        } else if (current <= 12) {
            statusText = 'Processando com IA...';
        } else if (current <= 24) {
            statusText = 'Revisando conteúdo...';
        } else if (current <= 36) {
            statusText = 'Finalizando roteiro...';
        } else if (current <= 48) {
            statusText = 'Quase pronto...';
        } else {
            statusText = 'Aguarde, processamento em andamento...';
        }

        document.getElementById('advancedProgressStatus').textContent = statusText;
    }

    function setProgressMessage(message, minPercent = 0, updateStatusText = true) {
        const progressBar = document.querySelector('#advancedProgressBar');
        const currentValue = parseFloat(progressBar.getAttribute('aria-valuenow')) || 0;
        const target = Math.max(currentValue, minPercent);

        progressBar.style.width = target + '%';
        progressBar.setAttribute('aria-valuenow', target);
        if (updateStatusText) {
            document.getElementById('advancedProgressStatus').textContent = message;
        }
    }

    function showArticleSearchMessage(message) {
        const articleStatus = document.getElementById('advancedArticleSearchStatus');
        if (!articleStatus) {
            return;
        }
        if (articleMessageTimeout) {
            clearTimeout(articleMessageTimeout);
            articleMessageTimeout = null;
        }
        articleStatus.textContent = message;
        articleStatus.style.display = 'block';
        articleMessageActive = true;
        articleMessageTimeout = setTimeout(() => {
            hideArticleSearchMessage();
        }, 15000);
    }

    function hideArticleSearchMessage() {
        const articleStatus = document.getElementById('advancedArticleSearchStatus');
        if (!articleStatus) {
            return;
        }
        if (articleMessageTimeout) {
            clearTimeout(articleMessageTimeout);
            articleMessageTimeout = null;
        }
        articleStatus.textContent = '';
        articleStatus.style.display = 'none';
        articleMessageActive = false;
    }

    /**
     * Iniciar animação progressiva inicial (enquanto aguarda polling)
     */
    function startInitialProgressAnimation() {
        stopInitialProgressAnimation(); // Limpar qualquer animação anterior

        initialProgressValue = 0;
        const progressBar = document.querySelector('#advancedProgressBar');
        if (!progressBar) return;

        // Resetar barra
        progressBar.style.width = '0%';
        progressBar.setAttribute('aria-valuenow', '0');

        // Animar gradualmente até 18% (para dar sensação de progresso)
        const targetProgress = 18;
        const duration = 8000; // 8 segundos para chegar a 18%
        const steps = 80; // 80 atualizações
        const stepDuration = duration / steps;
        const increment = targetProgress / steps;

        function animateStep() {
            if (!isPollingActive && initialProgressValue < targetProgress) {
                initialProgressValue += increment;
                const currentValue = Math.min(initialProgressValue, targetProgress);

                progressBar.style.width = currentValue + '%';
                progressBar.setAttribute('aria-valuenow', currentValue);

                // Atualizar mensagem de status baseado no progresso
                updateInitialProgressMessage(currentValue);

                initialProgressAnimation = setTimeout(animateStep, stepDuration);
            }
        }

        // Começar animação após pequeno delay
        initialProgressAnimation = setTimeout(animateStep, 100);
    }

    /**
     * Atualizar mensagem de status durante animação inicial
     */
    function updateInitialProgressMessage(progress) {
        const statusElement = document.getElementById('advancedProgressStatus');
        if (!statusElement) return;

        let message = 'Iniciando processamento...';
        if (progress > 3) {
            message = 'Preparando análise com IA...';
        }
        if (progress > 6) {
            message = 'Carregando dados do vídeo de referência...';
        }
        if (progress > 9) {
            message = 'Processando informações...';
        }
        if (progress > 12) {
            message = 'Aguarde, processamento em andamento...';
        }
        if (progress > 15) {
            message = 'Gerando roteiro avançado...';
        }

        statusElement.textContent = message;
    }

    /**
     * Parar animação progressiva inicial
     */
    function stopInitialProgressAnimation() {
        if (initialProgressAnimation) {
            clearTimeout(initialProgressAnimation);
            initialProgressAnimation = null;
        }
        initialProgressValue = 0;
    }

    /**
     * Parar polling
     */
    function stopPolling() {
        if (pollingTimeout) {
            clearTimeout(pollingTimeout);
            pollingTimeout = null;
        }
        isPollingActive = false;
        articleProgressShown = false;
        hideArticleSearchMessage();
        stopInitialProgressAnimation();
    }

    /**
     * Copiar roteiro para clipboard
     */
    function copyRoadmap() {
        const roadmapText = document.getElementById('advancedRoadmapResult').value;

        if (navigator.clipboard) {
            navigator.clipboard.writeText(roadmapText).then(function() {
                toastr.success('Roteiro avançado copiado!');
            }).catch(function() {
                fallbackCopyTextToClipboard(roadmapText, 'Roteiro avançado copiado!', 'Erro ao copiar roteiro');
            });
        } else {
            fallbackCopyTextToClipboard(roadmapText, 'Roteiro avançado copiado!', 'Erro ao copiar roteiro');
        }
    }

    /**
     * Atualizar roteiro no servidor (suggested, favorites ou user_roadmaps).
     * Usa roadmap_id quando disponível (dashboard.user.roadmaps.update), senão suggested.update com headline_id.
     */
    function updateRoadmap() {
        const content = (document.getElementById('advancedRoadmapResult') || {}).value || '';
        const roadmapIdEl = document.getElementById('advancedRoadmapIdForUpdate');
        const headlineIdEl = document.getElementById('advancedRoadmapHeadlineId');
        const saveToTableEl = document.getElementById('saveToTable');
        const headlineText = (document.getElementById('advancedRoadmapHeadlineResult') || document.getElementById('advancedRoadmapHeadline') || {}).value || 'Roteiro Avançado';

        const roadmapId = roadmapIdEl ? roadmapIdEl.value.trim() : '';
        const headlineId = headlineIdEl ? headlineIdEl.value.trim() : '';
        const saveToTable = saveToTableEl ? saveToTableEl.value : '';

        if (!content.trim()) {
            if (typeof toastr !== 'undefined') toastr.warning('Não há roteiro para atualizar.');
            return;
        }

        const btn = document.getElementById('btnUpdateRoadmap');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Salvando...';
        }

        const config = window.AdvancedRoadmapModalConfig || {};
        const routes = config.routes || {};
        const token = config.csrfToken || '';

        function done(success, message) {
            if (typeof toastr !== 'undefined') toastr[success ? 'success' : 'error'](message || (success ? 'Roteiro atualizado!' : 'Erro ao atualizar.'));
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="me-2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg> Atualizar Roteiro';
            }
        }

        if (roadmapId && routes.updateRoadmap) {
            $.ajax({
                url: routes.updateRoadmap,
                type: 'POST',
                data: {
                    _token: token,
                    id: roadmapId,
                    name: headlineText.substring(0, 255),
                    roadmap_gpt: content
                },
                success: function (data) {
                    done(data.success !== false, data.message || 'Roteiro atualizado com sucesso!');
                },
                error: function (xhr) {
                    const msg = xhr.responseJSON && (xhr.responseJSON.message || (xhr.responseJSON.errors && Object.values(xhr.responseJSON.errors).flat().join(' '))) ? (xhr.responseJSON.message || xhr.responseJSON.errors) : 'Erro ao atualizar roteiro.';
                    done(false, typeof msg === 'string' ? msg : 'Erro ao atualizar roteiro.');
                }
            });
            return;
        }

        if (headlineId && routes.updateSuggested) {
            $.ajax({
                url: routes.updateSuggested,
                type: 'POST',
                data: {
                    _token: token,
                    id: headlineId,
                    headline: headlineText,
                    roadmap: content
                },
                success: function (data) {
                    done(data.success !== false, data.message || 'Roteiro atualizado!');
                },
                error: function (xhr) {
                    done(false, xhr.responseJSON && xhr.responseJSON.message ? xhr.responseJSON.message : 'Erro ao atualizar.');
                }
            });
            return;
        }

        done(false, 'Nenhum ID disponível para atualizar (roteiro ainda não foi salvo ou contexto desconhecido).');
    }

    /**
     * Copiar fontes da pesquisa para clipboard
     */
    function copySources() {
        const sourcesElement = document.getElementById('advancedSearchSourcesContent');
        if (!sourcesElement) {
            toastr.error('Nenhuma fonte disponível para copiar');
            return;
        }

        // Obter o texto do elemento (remover HTML se necessário)
        let sourcesText = sourcesElement.innerText || sourcesElement.textContent || '';

        // Se estiver vazio, tentar pegar o HTML e converter para texto
        if (!sourcesText.trim()) {
            sourcesText = sourcesElement.innerHTML;
            // Criar elemento temporário para extrair texto do HTML
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = sourcesText;
            sourcesText = tempDiv.innerText || tempDiv.textContent || '';
        }

        if (!sourcesText.trim()) {
            toastr.warning('Nenhuma fonte disponível para copiar');
            return;
        }

        if (navigator.clipboard) {
            navigator.clipboard.writeText(sourcesText).then(function() {
                toastr.success('Fontes copiadas para clipboard!');
            }).catch(function() {
                fallbackCopyTextToClipboard(sourcesText, 'Fontes copiadas para clipboard!', 'Erro ao copiar fontes');
            });
        } else {
            fallbackCopyTextToClipboard(sourcesText, 'Fontes copiadas para clipboard!', 'Erro ao copiar fontes');
        }
    }

    /**
     * Abrir modo chat
     */
    function openChatMode(triggerElement) {
        const chatResourceId = document.getElementById('advancedRoadmapChatResourceId').value;
        const fallbackId = document.getElementById('advancedRoadmapHeadlineId').value;
        const targetId = chatResourceId || fallbackId;
        const resourceTypeField = document.getElementById('advancedRoadmapChatResourceType');
        const saveToField = document.getElementById('saveToTable');
        const resourceType = resourceTypeField?.value || saveToField?.value || 'eng_reversa_headlines';

        if (!targetId) {
            if (typeof toastr !== 'undefined') {
                toastr.warning('Nenhum roteiro disponível para o modo chat. Gere um roteiro primeiro.');
            }
            return;
        }

        if (typeof window.startChatMode === 'function') {
            window.startChatMode(targetId, resourceType, triggerElement || document.getElementById('advanced_roadmap_chat_button'));
            return;
        }

        const config = window.AdvancedRoadmapModalConfig || {};
        const routes = config.routes || {};
        const chatTemplate = routes.chat;

        if (!chatTemplate) {
            console.error('[AdvancedRoadmap] Rota para modo chat não configurada');
            if (typeof toastr !== 'undefined') {
                toastr.error('Não foi possível abrir o modo chat. Entre em contato com o suporte.');
            }
            return;
        }

        window.location.href = chatTemplate.replace('__ID__', targetId);
    }

    /**
     * Fallback para copiar texto (navegadores antigos)
     */
    function fallbackCopyTextToClipboard(text, successMessage = 'Conteúdo copiado!', errorMessage = 'Erro ao copiar') {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        textArea.style.position = "fixed";
        textArea.style.top = 0;
        textArea.style.left = 0;
        textArea.style.width = '2em';
        textArea.style.height = '2em';
        textArea.style.padding = 0;
        textArea.style.border = 'none';
        textArea.style.outline = 'none';
        textArea.style.boxShadow = 'none';
        textArea.style.background = 'transparent';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();

        try {
            document.execCommand('copy');
            toastr.success(successMessage);
        } catch (err) {
            toastr.error(errorMessage);
        }

        document.body.removeChild(textArea);
    }

    /**
     * Recriar roteiro
     */
    function recreateRoadmap() {
        const headlineId = document.getElementById('advancedRoadmapHeadlineId')?.value ?? '';
        const headlineText = document.getElementById('advancedRoadmapHeadlineResult')?.value ?? '';

        // Limpar campos e resetar perguntas
        generatedQuestions = [];
        const advancedRoadmapHeadline = document.getElementById('advancedRoadmapHeadline');
        if(advancedRoadmapHeadline) advancedRoadmapHeadline.value = headlineText;
        const selectedRoadmapOption = document.getElementById('selectedRoadmapOption');
        if(selectedRoadmapOption) selectedRoadmapOption.value = '';
        const simpleObservationsText = document.getElementById('simpleObservationsText');
        if(simpleObservationsText) simpleObservationsText.value = '';
        const autoSearchDirectionText = document.getElementById('autoSearchDirectionText');
        if(autoSearchDirectionText) autoSearchDirectionText.value = '';
        const advancedRoadmapChatResourceId = document.getElementById('advancedRoadmapChatResourceId');
        if(advancedRoadmapChatResourceId) advancedRoadmapChatResourceId.value = '';

        // Resetar navegação (mostrar opções principais, esconder botão voltar)
        const mainOptionsContainer = document.getElementById('mainOptionsContainer');
        if(mainOptionsContainer) mainOptionsContainer.style.display = 'block';
        const backToMainOptionsBtn = document.getElementById('backToMainOptionsBtn');
        if(backToMainOptionsBtn) backToMainOptionsBtn.style.display = 'none';

        // Resetar cards principais
        const mainOptionManual = document.getElementById('mainOptionManual');
        if(mainOptionManual) mainOptionManual.style.border = '3px solid transparent';
        const mainOptionAuto = document.getElementById('mainOptionAuto');
        if(mainOptionAuto) mainOptionAuto.style.border = '3px solid transparent';
        const manualSubOptions = document.getElementById('manualSubOptions');
        if(manualSubOptions) manualSubOptions.style.display = 'none';
        const autoSearchDirectionField = document.getElementById('autoSearchDirectionField');
        if(autoSearchDirectionField) autoSearchDirectionField.style.display = 'none';

        // Resetar estilo dos cards de sub-opção
        const optionSimpleObservations6 = document.getElementById('optionSimpleObservations');
        if (optionSimpleObservations6) {
            optionSimpleObservations6.style.border = '2px solid transparent';
        }
        const optionAdvancedQuestions = document.getElementById('optionAdvancedQuestions');
        if(optionAdvancedQuestions) optionAdvancedQuestions.style.border = '2px solid transparent';
        // Campo de observações agora está sempre visível no modo manual

        // Resetar busca avançada para padrão (desativada)
        const advancedSearchEnabled = document.getElementById('advancedSearchEnabled');
        if (advancedSearchEnabled) advancedSearchEnabled.value = '0';

        // Resetar texto do botão para padrão
        const btn = document.getElementById('createDefaultRoadmapBtn');
        btn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="me-2">
                <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                <path d="M12 5l0 14" />
                <path d="M5 12l14 0" />
            </svg>
            Criar Roteiro Padrão
        `;

        // Mostrar estado de formulário
        showState('form');
    }

    // Inicializar quando o documento estiver pronto
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    /**
     * Fechar biblioteca de vídeos (delegar para o módulo Library)
     */
    function closeLibrary() {
        if (window.AdvancedRoadmapLibrary) {
            window.AdvancedRoadmapLibrary.close();
        }
    }

    /**
     * Limpar vídeo selecionado (delegar para o módulo Library)
     */
    function clearSelectedVideo() {
        if (window.AdvancedRoadmapLibrary) {
            window.AdvancedRoadmapLibrary.clearSelectedVideo();
        }
    }

    /**
     * Traduz todos os resultados (title e snippet) de uma query específica
     * @param {number} queryIndex - Índice da query a ser traduzida
     * @param {string} searchBoxId - ID da caixa de busca (opcional, para buscas manuais)
     */
    function translateAllResults(queryIndex, searchBoxId = null) {
        const btnId = searchBoxId
            ? `translate_all_${searchBoxId}_${queryIndex}`
            : `translate_all_${queryIndex}`;
        const btn = document.getElementById(btnId);
        if (!btn) {
            console.error('[AdvancedRoadmap] Botão de tradução não encontrado para query:', queryIndex, 'searchBoxId:', searchBoxId);
            return;
        }

        // Desabilitar botão e mostrar loading
        const originalHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `
            <span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>
            Traduzindo...
        `;

        // Coletar todos os resultados desta query
        const results = [];
        const checkboxSelector = searchBoxId
            ? `.manual-link-checkbox[data-search-box-id="${searchBoxId}"][data-query-index="${queryIndex}"]`
            : `.link-checkbox[data-query-index="${queryIndex}"]`;
        const checkboxes = document.querySelectorAll(checkboxSelector);

        checkboxes.forEach((checkbox, resultIndex) => {
            const titleId = searchBoxId
                ? `${searchBoxId}_title_${queryIndex}_${resultIndex}`
                : `title_${queryIndex}_${resultIndex}`;
            const snippetId = searchBoxId
                ? `${searchBoxId}_snippet_${queryIndex}_${resultIndex}`
                : `snippet_${queryIndex}_${resultIndex}`;
            const originalTitle = checkbox.getAttribute('data-link-title') || '';
            const originalSnippet = checkbox.getAttribute('data-link-snippet') || '';

            if (originalTitle || originalSnippet) {
                results.push({
                    titleId: titleId,
                    snippetId: snippetId,
                    checkbox: checkbox,
                    originalTitle: originalTitle,
                    originalSnippet: originalSnippet
                });
            }
        });

        if (results.length === 0) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
            toastr.warning('Nenhum resultado para traduzir');
            return;
        }

        // Obter URL da rota de tradução
        const translateUrl = window.AdvancedRoadmapRoutes?.translateSearchResults
            || window.AdvancedRoadmapModalConfig?.routes?.translateSearchResults
            || '/dashboard/user/headlines/suggested/advanced-roadmap/translate-search-results';

        // Contador de traduções concluídas
        let completed = 0;
        let hasError = false;

        // Traduzir cada resultado
        results.forEach((result, index) => {
            $.ajax({
                url: translateUrl,
                type: 'POST',
                data: {
                    _token: window.AdvancedRoadmapModalConfig?.csrfToken || $('meta[name="csrf-token"]').attr('content'),
                    title: result.originalTitle,
                    snippet: result.originalSnippet
                },
                success: function(response) {
                    if (response.success && response.data) {
                        // Atualizar título se traduzido
                        if (response.data.title && result.titleId) {
                            const titleElement = document.getElementById(result.titleId);
                            if (titleElement) {
                                const svgElement = titleElement.querySelector('svg');
                                if (svgElement) {
                                    const svgClone = svgElement.cloneNode(true);
                                    titleElement.innerHTML = response.data.title + ' ';
                                    titleElement.appendChild(svgClone);
                                } else {
                                    titleElement.textContent = response.data.title;
                                }
                                // Atualizar data attribute do checkbox
                                result.checkbox.setAttribute('data-link-title', response.data.title);
                            }
                        }

                        // Atualizar snippet se traduzido
                        if (response.data.snippet && result.snippetId) {
                            const snippetElement = document.getElementById(result.snippetId);
                            if (snippetElement) {
                                snippetElement.textContent = response.data.snippet;
                                // Atualizar data attribute do checkbox
                                result.checkbox.setAttribute('data-link-snippet', response.data.snippet);
                            }
                        }
                    }

                    completed++;
                    checkCompletion();
                },
                error: function(xhr, status, error) {
                    console.error(`[AdvancedRoadmap] Erro ao traduzir resultado ${index + 1}:`, error);
                    hasError = true;
                    completed++;
                    checkCompletion();
                }
            });
        });

        // Verificar se todas as traduções foram concluídas
        function checkCompletion() {
            if (completed === results.length) {
                if (hasError) {
                    toastr.warning('Alguns resultados não puderam ser traduzidos');
                } else {
                    toastr.success(`${results.length} resultado(s) traduzido(s) com sucesso!`);
                }

                // Esconder botão após tradução
                btn.style.display = 'none';
            }
        }
    }

    // ============================================
    // FUNÇÕES DE BUSCA MANUAL SERPER
    // ============================================

    let searchBoxCounter = 0;
    let allManualSearchResults = {}; // Armazenar resultados de todas as buscas: { searchBoxId: { query, results, selectedLinks } }

    /**
     * Inicializar primeira caixa de busca manual
     */
    function initializeManualSearch() {
        const container = document.getElementById('manualSearchBoxesContainer');
        if (!container) return;

        container.innerHTML = '';
        searchBoxCounter = 0;
        allManualSearchResults = {};

        // Adicionar primeira caixa
        addNewSearchBox();
    }

    /**
     * Adicionar nova caixa de busca
     */
    function addNewSearchBox() {
        const container = document.getElementById('manualSearchBoxesContainer');
        if (!container) return;

        searchBoxCounter++;
        const searchBoxId = `searchBox_${searchBoxCounter}`;

        const headlineText = document.getElementById('advancedRoadmapHeadline')?.value || '';

        // Gerar sugestões baseadas na headline
        const suggestions = generateSearchSuggestions(headlineText);

        const searchBoxHTML = `
            <div class="card mb-3 border-2 border-purple" id="${searchBoxId}" data-search-box-id="${searchBoxId}">
                <div class="card-header bg-purple-lt d-flex justify-content-between align-items-center">
                    <h6 class="mb-0 fw-bold">
                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon me-2">
                            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                            <circle cx="12" cy="10" r="3"></circle>
                        </svg>
                        Busca ${searchBoxCounter}
                    </h6>
                    ${searchBoxCounter > 1 ? `
                        <button type="button" class="btn btn-sm btn-outline-danger" onclick="AdvancedRoadmapModal.removeSearchBox('${searchBoxId}')">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon">
                                <line x1="18" y1="6" x2="6" y2="18"></line>
                                <line x1="6" y1="6" x2="18" y2="18"></line>
                            </svg>
                        </button>
                    ` : ''}
                </div>
                <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label small fw-bold">Digite sua busca:</label>
                        <div class="input-group">
                            <input type="text"
                                   class="form-control"
                                   id="${searchBoxId}_query"
                                   placeholder="Ex: estudos sobre testosterona, benefícios do jejum intermitente..."
                                   onkeypress="if(event.key === 'Enter') AdvancedRoadmapModal.performManualSearch('${searchBoxId}')">
                            <button type="button"
                                    class="btn btn-purple"
                                    id="${searchBoxId}_searchBtn"
                                    onclick="AdvancedRoadmapModal.performManualSearch('${searchBoxId}')">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon me-1">
                                    <path d="M21 21l-6-6m2-5a7 7 0 1 1-14 0 7 7 0 0 1 14 0z"></path>
                                </svg>
                                Pesquisar
                            </button>
                        </div>
                        ${suggestions.length > 0 ? `
                            <div class="mt-2">
                                <small class="text-muted d-block mb-1">💡 Sugestões:</small>
                                <div class="d-flex flex-wrap gap-1">
                                    ${suggestions.map(suggestion => `
                                        <button type="button"
                                                class="btn btn-sm btn-outline-secondary suggestion-btn"
                                                onclick="document.getElementById('${searchBoxId}_query').value = '${suggestion.replace(/'/g, "\\'")}'; AdvancedRoadmapModal.performManualSearch('${searchBoxId}')">
                                            ${suggestion}
                                        </button>
                                    `).join('')}
                                </div>
                            </div>
                        ` : ''}
                    </div>

                    <!-- Loading state -->
                    <div id="${searchBoxId}_loading" style="display: none;" class="text-center py-3">
                        <div class="spinner-border spinner-border-sm text-purple mb-2" role="status"></div>
                        <small class="text-muted d-block">Buscando na internet...</small>
                    </div>

                    <!-- Results container -->
                    <div id="${searchBoxId}_results" style="display: none;">
                        <!-- Resultados serão inseridos aqui -->
                    </div>
                </div>
            </div>
        `;

        container.insertAdjacentHTML('beforeend', searchBoxHTML);
    }

    /**
     * Remover caixa de busca
     */
    function removeSearchBox(searchBoxId) {
        const searchBox = document.getElementById(searchBoxId);
        if (searchBox) {
            searchBox.remove();
            // Remover resultados dessa busca
            delete allManualSearchResults[searchBoxId];
        }
    }

    /**
     * Gerar sugestões de busca baseadas na headline
     */
    function generateSearchSuggestions(headlineText) {
        if (!headlineText || headlineText.trim().length < 10) {
            return [];
        }

        const suggestions = [];
        const headlineLower = headlineText.toLowerCase();

        // Extrair palavras-chave principais
        const words = headlineText.split(/\s+/).filter(w => w.length > 4);

        if (words.length > 0) {
            // Sugestão 1: Busca direta
            suggestions.push(headlineText.substring(0, 60));

            // Sugestão 2: Adicionar "benefícios" se não tiver
            if (!headlineLower.includes('benefício') && !headlineLower.includes('vantagem')) {
                suggestions.push(`benefícios ${words[0]} ${words.length > 1 ? words[1] : ''}`);
            }

            // Sugestão 3: Adicionar "estudos" se for tema de saúde
            if (headlineLower.includes('saúde') || headlineLower.includes('testosterona') || headlineLower.includes('hormônio')) {
                suggestions.push(`estudos científicos ${words[0]}`);
            }
        }

        return suggestions.slice(0, 3); // Máximo 3 sugestões
    }

    /**
     * Realizar busca manual no Serper
     */
    function performManualSearch(searchBoxId) {
        const queryInput = document.getElementById(`${searchBoxId}_query`);
        if (!queryInput) return;

        const query = queryInput.value.trim();
        if (!query) {
            toastr.warning('Digite uma busca antes de pesquisar');
            return;
        }

        // Mostrar loading
        const loadingEl = document.getElementById(`${searchBoxId}_loading`);
        const resultsEl = document.getElementById(`${searchBoxId}_results`);
        const searchBtn = document.getElementById(`${searchBoxId}_searchBtn`);

        if (loadingEl) loadingEl.style.display = 'block';
        if (resultsEl) resultsEl.style.display = 'none';
        if (searchBtn) searchBtn.disabled = true;

        // Buscar diretamente no Serper (busca literal como Google)
        const directSearchUrl = window.AdvancedRoadmapModalConfig?.routes?.directSearch
            || '/dashboard/user/headlines/suggested/advanced-roadmap/direct-search';

        $.ajax({
            url: directSearchUrl,
            type: 'POST',
            data: {
                _token: window.AdvancedRoadmapModalConfig.csrfToken,
                query: query, // Query exata que o usuário digitou
                gl: 'br', // País: Brasil
                hl: 'pt-br' // Idioma: Português
            },
            success: function(response) {
                if (loadingEl) loadingEl.style.display = 'none';
                if (searchBtn) searchBtn.disabled = false;

                if (response.success && response.data) {
                    // Processar resultados para o formato esperado
                    const processedData = processDirectSearchResults(response.data, query);

                    // Armazenar resultados
                    allManualSearchResults[searchBoxId] = {
                        query: query,
                        data: processedData,
                        selectedLinks: []
                    };

                    // Exibir resultados
                    displayManualSearchResults(searchBoxId, processedData);
                } else {
                    toastr.error('Nenhum resultado encontrado para esta busca');
                    if (resultsEl) resultsEl.style.display = 'none';
                }
            },
            error: function(xhr, status, error) {
                console.error('[AdvancedRoadmap] Erro na busca manual:', error);
                if (loadingEl) loadingEl.style.display = 'none';
                if (searchBtn) searchBtn.disabled = false;
                toastr.error('Erro ao buscar na internet. Tente novamente.');
            }
        });
    }

    /**
     * Processar resultados de busca direta do Serper para exibição
     */
    function processDirectSearchResults(data, query) {
        // Resultados diretos do Serper vêm no formato { organic: [...] }
        const organic = data.organic || [];

        return {
            queries: [{
                posicao: 1,
                item_pt: query.substring(0, 50),
                descricao: 'Resultados da busca',
                query: query,
                idioma: 'pt',
                tipo: 'google',
                result: organic
            }]
        };
    }

    /**
     * Exibir resultados de uma busca manual
     */
    function displayManualSearchResults(searchBoxId, data) {
        const resultsEl = document.getElementById(`${searchBoxId}_results`);
        if (!resultsEl) return;

        if (!data || !data.queries || !Array.isArray(data.queries)) {
            resultsEl.innerHTML = '<div class="alert alert-warning">Nenhum resultado encontrado</div>';
            resultsEl.style.display = 'block';
            return;
        }

        let html = '<div class="mt-3"><h6 class="mb-3 fw-bold">📋 Resultados da busca:</h6>';

        data.queries.forEach((queryItem, queryIndex) => {
            const itemPt = queryItem.item_pt || `Busca ${queryIndex + 1}`;
            const results = queryItem.result || [];
            const needsTranslation = queryItem.idioma && queryItem.idioma !== 'pt' && queryItem.idioma !== 'br';

            if (results.length === 0) {
                return;
            }

            html += `
                <div class="card mb-3 border-purple">
                    <div class="d-flex card-header bg-purple-lt">
                        <div class="d-flex w-full flex-column">
                            <div class="row mb-2">
                                <div class="col-6">
                                    <h6 class="mb-0 fw-bold d-flex align-items-center">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon me-2">
                                            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                                            <circle cx="12" cy="10" r="3"></circle>
                                        </svg>
                                        ${itemPt}
                                    </h6>
                                </div>
                                <div class="col-6 text-end d-flex align-items-center justify-content-end gap-2">
                                    ${needsTranslation ? `
                                        <button type="button"
                                                class="btn btn-sm btn-primary translate-all-btn"
                                                id="translate_all_${searchBoxId}_${queryIndex}"
                                                onclick="AdvancedRoadmapModal.translateAllResults(${queryIndex}, '${searchBoxId}')"
                                                title="Traduzir todos os resultados para português">
                                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon me-1">
                                                <path d="M5 8l6 6"></path>
                                                <path d="M4 14l6-6 2-3"></path>
                                                <path d="M2 5h12"></path>
                                                <path d="M7 2h1v6H7z"></path>
                                                <path d="M22 22l-5-10-5 10"></path>
                                                <path d="M14 18h6"></path>
                                            </svg>
                                            Traduzir
                                        </button>
                                    ` : ''}
                                </div>
                            </div>
                            <div class="row text-end align-items-center justify-content-center">
                                <div class="col-12 align-items-center justify-content-center">
                                    <div class="d-flex gap-2">
                                        <span class="badge bg-purple text-white">${results.length} ${results.length === 1 ? 'link encontrado' : 'links encontrados'}</span>
                                        <span class="badge bg-info text-white" id="${searchBoxId}_selectedCount_${queryIndex}">0/${MAX_SELECTED_LINKS_PER_CATEGORY} selecionados</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="card-body" style="max-height: 400px; overflow-y: auto;">
                        <div class="list-group list-group-flush">
                            ${results.map((result, resultIndex) => {
                                const linkId = `${searchBoxId}_link_${queryIndex}_${resultIndex}`;
                                const titleId = `${searchBoxId}_title_${queryIndex}_${resultIndex}`;
                                const snippetId = `${searchBoxId}_snippet_${queryIndex}_${resultIndex}`;
                                return `
                                    <div class="list-group-item px-0">
                                        <div class="form-check">
                                            <input class="form-check-input manual-link-checkbox" type="checkbox"
                                                id="${linkId}"
                                                data-search-box-id="${searchBoxId}"
                                                data-link-url="${result.link || ''}"
                                                data-link-title="${(result.title || '').replace(/"/g, '&quot;')}"
                                                data-link-snippet="${(result.snippet || '').replace(/"/g, '&quot;')}"
                                                data-query-posicao="${queryItem.posicao}"
                                                data-query-item-pt="${queryItem.item_pt || ''}"
                                                data-query-index="${queryIndex}"
                                                onchange="AdvancedRoadmapModal.updateManualSearchSelection('${searchBoxId}')">
                                            <label class="form-check-label w-100" for="${linkId}">
                                                <div class="d-flex justify-content-between align-items-start">
                                                    <div class="flex-fill">
                                                        <a href="${result.link || '#'}" target="_blank"
                                                            class="text-decoration-none fw-bold text-primary"
                                                            onclick="event.stopPropagation()"
                                                            id="${titleId}">
                                                            ${result.title || 'Sem título'}
                                                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon ms-1">
                                                                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                                                                <polyline points="15 3 21 3 21 9"></polyline>
                                                                <line x1="10" y1="14" x2="21" y2="3"></line>
                                                            </svg>
                                                        </a>
                                                        ${result.snippet ? `<p class="text-muted small mb-0 mt-1" id="${snippetId}">${result.snippet.substring(0, 150)}${result.snippet.length > 150 ? '...' : ''}</p>` : ''}
                                                    </div>
                                                </div>
                                            </label>
                                        </div>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    </div>
                </div>
            `;
        });

        html += '</div>';
        resultsEl.innerHTML = html;
        resultsEl.style.display = 'block';
    }

    /**
     * Atualizar seleção de links de uma busca manual
     */
    function updateManualSearchSelection(searchBoxId) {
        if (!allManualSearchResults[searchBoxId]) return;

        const selectedLinks = [];
        const checkboxes = document.querySelectorAll(`.manual-link-checkbox[data-search-box-id="${searchBoxId}"]:checked`);

        checkboxes.forEach(checkbox => {
            selectedLinks.push({
                url: checkbox.dataset.linkUrl,
                title: checkbox.dataset.linkTitle,
                snippet: checkbox.dataset.linkSnippet,
                query_posicao: checkbox.dataset.queryPosicao,
                query_item_pt: checkbox.dataset.queryItemPt
            });
        });

        allManualSearchResults[searchBoxId].selectedLinks = selectedLinks;

        // Atualizar contador
        const queryIndex = checkboxes.length > 0 ? checkboxes[0].dataset.queryIndex : 0;
        const countEl = document.getElementById(`${searchBoxId}_selectedCount_${queryIndex}`);
        if (countEl) {
            const count = selectedLinks.length;
            countEl.textContent = `${count}/${MAX_SELECTED_LINKS_PER_CATEGORY} selecionados`;
            if (count >= MAX_SELECTED_LINKS_PER_CATEGORY) {
                countEl.className = 'badge bg-success text-white';
            } else if (count > 0) {
                countEl.className = 'badge bg-info text-white';
            } else {
                countEl.className = 'badge bg-secondary text-white';
            }
        }

        // Desabilitar checkboxes quando atingir limite
        const allCheckboxes = document.querySelectorAll(`.manual-link-checkbox[data-search-box-id="${searchBoxId}"]`);
        allCheckboxes.forEach(checkbox => {
            const queryIdx = checkbox.dataset.queryIndex;
            const categorySelected = Array.from(document.querySelectorAll(`.manual-link-checkbox[data-search-box-id="${searchBoxId}"][data-query-index="${queryIdx}"]:checked`)).length;
            checkbox.disabled = categorySelected >= MAX_SELECTED_LINKS_PER_CATEGORY && !checkbox.checked;
        });
    }

    /**
     * Coletar todos os resultados das buscas manuais para enviar no request
     */
    function collectAllManualSearchResults() {
        const allResults = {
            queries: [],
            selected_links: []
        };

        Object.keys(allManualSearchResults).forEach(searchBoxId => {
            const searchData = allManualSearchResults[searchBoxId];
            if (searchData.data && searchData.data.queries) {
                allResults.queries.push(...searchData.data.queries);
            }
            if (searchData.selectedLinks && searchData.selectedLinks.length > 0) {
                allResults.selected_links.push(...searchData.selectedLinks);
            }
        });

        return allResults;
    }

    // API pública
    return {
        open: open,
        openWithCustomHeadline: openWithCustomHeadline,
        openForReprocess: openForReprocess,
        selectMainOption: selectMainOption,
        backToMainOptions: backToMainOptions,
        selectOption: selectOption,
        selectSearchProvider: selectSearchProvider,
        selectSearchType: selectSearchType,
        continueWithOption: continueWithOption,
        createDefaultRoadmap: createDefaultRoadmap,
        generateQuestions: generateQuestions,
        saveRoadmap: saveRoadmap,
        copyRoadmap: copyRoadmap,
        updateRoadmap: updateRoadmap,
        copySources: copySources,
        recreateRoadmap: recreateRoadmap,
        openChatMode: openChatMode,
        closeLibrary: closeLibrary,
        clearSelectedVideo: clearSelectedVideo,
        translateAllResults: translateAllResults,
        addNewSearchBox: addNewSearchBox,
        removeSearchBox: removeSearchBox,
        performManualSearch: performManualSearch,
        updateManualSearchSelection: updateManualSearchSelection,
        collectAllManualSearchResults: collectAllManualSearchResults,
        submitRoadmapSteps: submitRoadmapSteps,
        selectSourceType: selectSourceType,
        addMoreLinkField: addMoreLinkField
    };
})();

window.AdvancedRoadmapModal = AdvancedRoadmapModal;

// Confirmar que o módulo foi carregado com sucesso
console.log('[AdvancedRoadmapModal] Módulo carregado com sucesso', {
    timestamp: new Date().toISOString(),
    version: '1.0.0'
});



