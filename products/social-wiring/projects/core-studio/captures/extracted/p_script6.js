
        // ─── Globals ─────────────────────────────────────────────────────────────────
        window.allProfiles = [];
        window.currentProfilePage = 1;
        window.profilesPerPage = 24;
        window.profileSearchTerm = '';
        window.selectedNicheIds = [];
        window.selectedProfessionIds = [];
        window.profileNicheSelect = null;
        window.profileProfessionSelect = null;

        // ─── Init ─────────────────────────────────────────────────────────────────────
        document.addEventListener('DOMContentLoaded', async function () {
            initializeProfileFilters();

            // Pré-selecionar nichos/profissões do usuário
            try {
                const res = await fetch('/dashboard/user/profile/get-niches-professions', {
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    }
                });
                const data = await res.json();
                if (data.success && data.data) {
                    setTimeout(() => {
                        const nicheIds = data.data.niches || [];
                        const professionIds = data.data.professions || [];
                        if (nicheIds.length > 0 && window.profileNicheSelect) {
                            window.profileNicheSelect.setValue(nicheIds, true);
                            window.selectedNicheIds = nicheIds.map(String);
                        }
                        if (professionIds.length > 0 && window.profileProfessionSelect) {
                            window.profileProfessionSelect.setValue(professionIds, true);
                            window.selectedProfessionIds = professionIds.map(String);
                        }
                        updateClearButtonState();
                        if ((nicheIds.length > 0 || professionIds.length > 0) && window.allProfiles.length > 0) {
                            renderProfiles();
                        }
                    }, 500);
                }
            } catch (e) {
                console.warn('Erro ao buscar filtros do usuário:', e);
            }

            // Carregar perfis aprovados
            try {
                const res = await fetch('/dashboard/user/searches/approved-profiles', {
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    }
                });
                const data = await res.json();
                const loading = document.getElementById('extract-profiles-loading');
                const content = document.getElementById('extract-profiles-content');
                const empty   = document.getElementById('extract-profiles-empty');

                if (data.success && data.data && data.data.length > 0) {
                    window.allProfiles = data.data;
                    window.currentProfilePage = 1;
                    renderProfiles();
                    updateClearButtonState();
                    loading.style.display = 'none';
                    content.style.display = 'block';
                } else {
                    loading.style.display = 'none';
                    empty.style.display = 'block';
                }
            } catch (error) {
                console.error('Erro ao buscar perfis:', error);
                document.getElementById('extract-profiles-loading').style.display = 'none';
                document.getElementById('extract-profiles-empty').style.display = 'block';
                toastr.error('Erro ao carregar perfis. Tente novamente.');
            }
        });

        // ─── Filtros ─────────────────────────────────────────────────────────────────
        function updateClearButtonState() {
            const hasFilters = window.profileSearchTerm ||
                (window.selectedNicheIds && window.selectedNicheIds.length > 0) ||
                (window.selectedProfessionIds && window.selectedProfessionIds.length > 0);
            document.querySelectorAll('.btn-outline-danger[onclick="clearProfileSearch()"]').forEach(btn => {
                hasFilters ? btn.classList.add('has-filters') : btn.classList.remove('has-filters');
            });
        }

        function initializeProfileFilters() {
            if (typeof TomSelect === 'undefined') { setTimeout(initializeProfileFilters, 100); return; }
            if (window.profileNicheSelect) window.profileNicheSelect.destroy();
            if (window.profileProfessionSelect) window.profileProfessionSelect.destroy();

            const nicheEl      = document.getElementById('profile-filter-niche');
            const professionEl = document.getElementById('profile-filter-profession');
            if (!nicheEl || !professionEl) { setTimeout(initializeProfileFilters, 100); return; }

            window.profileNicheSelect = new TomSelect('#profile-filter-niche', {
                copyClassesToDropdown: false, dropdownParent: 'body', create: false,
                placeholder: 'Selecione os nichos...',
                onChange: function (values) {
                    window.selectedNicheIds = values || [];
                    window.currentProfilePage = 1;
                    updateClearButtonState();
                    renderProfiles();
                },
                render: { option: function (data, escape) { return `<div class="option">${escape(data.text)}</div>`; } }
            });

            window.profileProfessionSelect = new TomSelect('#profile-filter-profession', {
                copyClassesToDropdown: false, dropdownParent: 'body', create: false,
                placeholder: 'Selecione as profissões...',
                onChange: function (values) {
                    window.selectedProfessionIds = values || [];
                    window.currentProfilePage = 1;
                    updateClearButtonState();
                    renderProfiles();
                },
                render: { option: function (data, escape) { return `<div class="option">${escape(data.text)}</div>`; } }
            });
        }

        function filterProfiles() {
            const input = document.getElementById('profile-search-input');
            if (input) { window.profileSearchTerm = input.value.toLowerCase().trim(); window.currentProfilePage = 1; updateClearButtonState(); renderProfiles(); }
        }

        function clearProfileSearch() {
            const input = document.getElementById('profile-search-input');
            if (input) input.value = '';
            window.profileSearchTerm = '';
            if (window.profileNicheSelect) window.profileNicheSelect.clear();
            if (window.profileProfessionSelect) window.profileProfessionSelect.clear();
            window.selectedNicheIds = [];
            window.selectedProfessionIds = [];
            window.currentProfilePage = 1;
            updateClearButtonState();
            renderProfiles();
        }

        function changeProfilePage(page) {
            window.currentProfilePage = page;
            renderProfiles();
            const c = document.getElementById('profiles-container');
            if (c) c.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        // ─── Render de cards ──────────────────────────────────────────────────────────
        function renderProfiles() {
            const container          = document.getElementById('profiles-container');
            const paginationContainer = document.getElementById('profiles-pagination');
            if (!container || !window.allProfiles || window.allProfiles.length === 0) {
                if (container) container.innerHTML = '';
                if (paginationContainer) paginationContainer.style.display = 'none';
                return;
            }

            let filtered = window.allProfiles;
            if (window.profileSearchTerm) {
                filtered = filtered.filter(p => (p.profile || '').toLowerCase().includes(window.profileSearchTerm));
            }
            if (window.selectedNicheIds && window.selectedNicheIds.length > 0) {
                filtered = filtered.filter(p =>
                    p.niche_ids && p.niche_ids.some(id => window.selectedNicheIds.includes(String(id)))
                );
            }
            if (window.selectedProfessionIds && window.selectedProfessionIds.length > 0) {
                filtered = filtered.filter(p =>
                    p.profession_ids && p.profession_ids.some(id => window.selectedProfessionIds.includes(String(id)))
                );
            }

            if (filtered.length === 0) {
                const parts = [];
                if (window.profileSearchTerm) parts.push(`com o termo "${window.profileSearchTerm}"`);
                if (window.selectedNicheIds.length > 0) parts.push('com os nichos selecionados');
                if (window.selectedProfessionIds.length > 0) parts.push('com as profissões selecionadas');
                container.innerHTML = `
                    <div class="col-12 text-center py-5">
                        <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-lg text-muted mb-3" width="48" height="48" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor" fill="none">
                            <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                            <path d="M10 10m-7 0a7 7 0 1 0 14 0a7 7 0 1 0 -14 0"/>
                            <path d="M21 21l-6 -6"/>
                        </svg>
                        <p class="text-muted">Nenhum perfil encontrado${parts.length ? ' ' + parts.join(' e ') : ''}.</p>
                    </div>`;
                if (paginationContainer) paginationContainer.style.display = 'none';
                return;
            }

            const totalPages  = Math.ceil(filtered.length / window.profilesPerPage);
            const startIndex  = (window.currentProfilePage - 1) * window.profilesPerPage;
            const paginated   = filtered.slice(startIndex, startIndex + window.profilesPerPage);
            container.innerHTML = '';

            paginated.forEach(profile => {
                const card = document.createElement('div');
                card.className = 'col-md-6 col-lg-4 mb-4';

                let thumbsHtml = '';
                (profile.thumbnails || []).forEach((t, i) => {
                    thumbsHtml += `<div class="thumbnail-item" style="flex:1;min-width:0;"><img src="${t}" alt="Thumb ${i+1}" class="img-fluid rounded" style="width:100%;height:120px;object-fit:cover;" onerror="this.src='/back/static/placeholder.jpg'"></div>`;
                });
                for (let i = (profile.thumbnails || []).length; i < 3; i++) {
                    thumbsHtml += `<div class="thumbnail-item" style="flex:1;min-width:0;background:#f3f4f6;border-radius:4px;display:flex;align-items:center;justify-content:center;">
                        <svg xmlns="http://www.w3.org/2000/svg" class="icon text-muted" width="32" height="32" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 4m0 2a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2z"/><path d="M4 8l4 -4l4 4l4 -4l4 4"/></svg>
                    </div>`;
                }

                const socialIcon = profile.social === 'instagram'
                    ? `<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 4m0 4a4 4 0 0 1 4 -4h8a4 4 0 0 1 4 4v8a4 4 0 0 1 -4 4h-8a4 4 0 0 1 -4 -4z"/><path d="M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0 -6 0"/><path d="M16.5 7.5l0 .01"/></svg>`
                    : `<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M9 2m0 4a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v4a4 4 0 0 1 -4 4h-4a4 4 0 0 1 -4 -4z"/><path d="M9 18m0 4a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v4a4 4 0 0 1 -4 4h-4a4 4 0 0 1 -4 -4z"/><path d="M9 10m-4 0a4 4 0 1 0 8 0a4 4 0 1 0 -8 0"/></svg>`;

                card.innerHTML = `
                    <div class="card h-100" style="transition:transform .2s,box-shadow .2s;position:relative;"
                         onmouseover="this.style.transform='translateY(-4px)';this.style.boxShadow='0 4px 12px rgba(0,0,0,0.15)'"
                         onmouseout="this.style.transform='';this.style.boxShadow=''">
                        <div class="card-body p-3">
                            <div class="d-flex align-items-center mb-3">
                                <div class="me-2">${socialIcon}</div>
                                <h5 class="card-title mb-0 flex-grow-1">@${profile.profile}</h5>
                            </div>
                            <div class="thumbnails-container mb-3" style="display:flex;gap:4px;height:120px;">${thumbsHtml}</div>
                            <div class="d-flex gap-2 mt-1">
                                <a href="/dashboard/user/library?profile=${profile.profile}" target="_blank" title="Ver vídeos deste perfil"
                                   style="flex:1;display:flex;align-items:center;justify-content:center;gap:5px;height:36px;border-radius:20px;font-size:0.78rem;font-weight:600;text-decoration:none;background:linear-gradient(135deg,#6d28d9,#7c3aed);color:#fff;border:none;transition:opacity .2s;"
                                   onmouseover="this.style.opacity='.85'" onmouseout="this.style.opacity='1'">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M10 12a2 2 0 1 0 4 0a2 2 0 0 0 -4 0"/><path d="M21 12c-2.4 4 -5.4 6 -9 6c-3.6 0 -6.6 -2 -9 -6c2.4 -4 5.4 -6 9 -6c3.6 0 6.6 2 9 6"/></svg>
                                    Vídeos
                                </a>
                                <button type="button"
                                        onclick="openProfileViralSearch('${profile.profile}', ${profile.eng_reversa_search_id})"
                                        title="Ver pesquisa extraída deste perfil"
                                        style="flex:1;display:flex;align-items:center;justify-content:center;gap:5px;height:36px;border-radius:20px;font-size:0.78rem;font-weight:600;background:linear-gradient(135deg,#0d9488,#14b8a6);color:#fff;border:none;cursor:pointer;transition:opacity .2s;"
                                        onmouseover="this.style.opacity='.85'" onmouseout="this.style.opacity='1'">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M9 5h-2a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-12a2 2 0 0 0 -2 -2h-2"/><path d="M9 3m0 2a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2v0a2 2 0 0 1 -2 2h-2a2 2 0 0 1 -2 -2z"/><path d="M9 12l.01 0"/><path d="M13 12l2 0"/><path d="M9 16l.01 0"/><path d="M13 16l2 0"/></svg>
                                    Pesquisa
                                </button>
                            </div>
                        </div>
                    </div>`;
                container.appendChild(card);
            });

            // Paginação
            if (totalPages > 1 && paginationContainer) {
                const cur = window.currentProfilePage;
                const prevChevron = `<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M15 6l-6 6l6 6"/></svg>`;
                const nextChevron = `<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="20" height="20" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M9 6l6 6l-6 6"/></svg>`;

                let html = '<nav><ul class="pagination mb-0">';
                html += cur > 1 ? `<li class="page-item"><a class="page-link" href="javascript:void(0);" onclick="changeProfilePage(${cur-1})">${prevChevron}</a></li>` : `<li class="page-item disabled"><span class="page-link">${prevChevron}</span></li>`;

                let sp = Math.max(1, cur - 2), ep = Math.min(totalPages, cur + 2);
                if (sp > 1) { html += `<li class="page-item"><a class="page-link" href="javascript:void(0);" onclick="changeProfilePage(1)">1</a></li>`; if (sp > 2) html += `<li class="page-item disabled"><span class="page-link">...</span></li>`; }
                for (let i = sp; i <= ep; i++) html += i === cur ? `<li class="page-item active"><span class="page-link">${i}</span></li>` : `<li class="page-item"><a class="page-link" href="javascript:void(0);" onclick="changeProfilePage(${i})">${i}</a></li>`;
                if (ep < totalPages) { if (ep < totalPages - 1) html += `<li class="page-item disabled"><span class="page-link">...</span></li>`; html += `<li class="page-item"><a class="page-link" href="javascript:void(0);" onclick="changeProfilePage(${totalPages})">${totalPages}</a></li>`; }

                html += cur < totalPages ? `<li class="page-item"><a class="page-link" href="javascript:void(0);" onclick="changeProfilePage(${cur+1})">${nextChevron}</a></li>` : `<li class="page-item disabled"><span class="page-link">${nextChevron}</span></li>`;
                html += `</ul></nav><div class="text-center mt-2 text-muted small">Mostrando ${startIndex+1}-${Math.min(startIndex+window.profilesPerPage, filtered.length)} de ${filtered.length} perfil(is)</div>`;
                paginationContainer.innerHTML = html;
                paginationContainer.style.display = 'flex';
            } else if (paginationContainer) {
                paginationContainer.style.display = 'none';
            }
        }

        // ─── Modal Pesquisa (pvs) ─────────────────────────────────────────────────────
        let _pvsItems = [];
        let _pvsSelectedKeys = new Set();

        async function openProfileViralSearch(profile, engReversaSearchId) {
            document.getElementById('pvs-profile-name').textContent = '@' + profile;
            document.getElementById('pvs-loading').style.display = 'flex';
            document.getElementById('pvs-empty').style.display = 'none';
            document.getElementById('pvs-content').style.display = 'none';
            document.getElementById('pvs-save-btn').style.display = 'none';
            document.getElementById('pvs-selected-count').textContent = '0';
            document.getElementById('pvs-select-all-label').textContent = 'Selecionar todos';
            _pvsItems = [];
            _pvsSelectedKeys = new Set();

            const modal = new bootstrap.Modal(document.getElementById('profileViralSearchModal'));
            modal.show();

            try {
                const res  = await fetch(`/dashboard/user/searches/profile-viral-search/${engReversaSearchId}`, {
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
                const total = _pvsItems.reduce((s, g) => s + g.items.length, 0);
                document.getElementById('pvs-count').textContent = `${_pvsItems.length} variável(is) · ${total} item(s)`;
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
            const vm = escaped ? new RegExp(escaped, 'i').exec(headline) : null;
            if (!vm) return headline;
            const vs = vm.index, ve = vs + vm[0].length;
            const before = headline.slice(0, vs);
            const lpm = [...before.matchAll(/[.?!]/g)].pop();
            const lc = lpm ? lpm.index + 1 : 0;
            const minR = Math.max(ve, lc + 30);
            const rr = /[.?!]/g; rr.lastIndex = minR;
            const rm = rr.exec(headline);
            return headline.slice(lc, rm ? rm.index + 1 : headline.length).trimStart();
        }

        function highlightViralTopic(headline, value) {
            if (!headline) return '<span style="color:rgba(255,255,255,0.35);">—</span>';
            const dim  = t => `<span style="color:rgba(255,255,255,0.42);font-weight:400;">${t}</span>`;
            const bold = t => `<strong style="color:#e9d5ff;font-weight:700;">${t}</strong>`;
            if (!value) return dim(headline);
            const esc = value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const rx  = new RegExp(`(${esc})`, 'i');
            const parts = headline.split(rx);
            if (parts.length === 1) return dim(headline) + ' ' + bold(`[${value}]`);
            return parts.map(p => rx.test(p) ? bold(p) : dim(p)).join('');
        }

        function formatPlays(n) {
            if (!n) return '0';
            const num = parseInt(n);
            if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
            if (num >= 1000)    return (num / 1000).toFixed(1) + 'K';
            return num.toLocaleString('pt-BR');
        }

        function renderPvsItem(item, variableId, ii) {
            const added   = !!item.already_added;
            const key     = `${item.result_id}_${variableId}`;
            const checkId = `pvs-chk-${key}-${ii}`;
            const thumb   = item.thumbnail
                ? `<img src="${item.thumbnail}" alt="thumb" style="width:64px;height:64px;object-fit:cover;border-radius:6px;flex-shrink:0;${added ? 'opacity:0.4;' : ''}" onerror="this.src='/back/static/placeholder.jpg'">`
                : `<div style="width:64px;height:64px;background:#1a1a2e;border-radius:6px;flex-shrink:0;display:flex;align-items:center;justify-content:center;${added ? 'opacity:0.4;' : ''}"><svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M7 4v16l13 -8z"/></svg></div>`;
            const rowStyle = added ? 'border-bottom:1px solid rgba(255,255,255,0.04);opacity:0.55;' : 'border-bottom:1px solid rgba(255,255,255,0.05);';
            const valStyle = added ? 'font-size:0.93rem;color:rgba(255,255,255,0.35);text-decoration:line-through;' : 'font-size:0.93rem;color:#e9d5ff;';
            const chk      = added
                ? `<input type="checkbox" disabled checked style="width:16px;height:16px;flex-shrink:0;margin-top:4px;opacity:0.4;cursor:not-allowed;">`
                : `<input class="form-check-input pvs-checkbox flex-shrink-0 mt-1" type="checkbox" id="${checkId}" data-result-id="${item.result_id}" data-variable-id="${variableId}" data-content="${(item.value||'').replace(/"/g,'&quot;')}" data-plays="${item.plays??''}" data-key="${key}-${ii}" onchange="onPvsCheckboxChange(this)" style="width:16px;height:16px;cursor:pointer;">`;
            const badge = added ? `<span style="font-size:0.68rem;color:rgba(255,255,255,0.4);display:flex;align-items:center;gap:3px;">✓ Já adicionado</span>` : '';
            return `
                <div class="d-flex gap-3 align-items-start py-3" data-pvs-row="1" style="${rowStyle}">
                    ${chk}${thumb}
                    <label ${added ? '' : `for="${checkId}"`} class="mb-0 flex-grow-1" style="${added ? 'cursor:default;' : 'cursor:pointer;'}line-height:1;">
                        <div class="pvs-item-title fw-bold mb-1" style="${valStyle}">${item.value||'—'}</div>
                        <div class="mb-2" style="font-size:0.8rem;line-height:1.45;${added ? 'opacity:0.5;' : ''}">
                            ${highlightViralTopic(truncateHeadline(item.headline, item.value), item.value)}
                        </div>
                        <div class="pvs-item-meta d-flex align-items-center gap-2">
                            <span class="badge bg-purple-lt" style="font-size:0.68rem;${added ? 'opacity:0.5;' : ''}">
                                <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M7 4v16l13 -8z"/></svg>
                                ${formatPlays(item.plays)}
                            </span>
                            ${item.result_id ? `<a href="/dashboard/user/library?viral_result_id=${item.result_id}" target="_blank" style="font-size:0.72rem;color:${added ? 'rgba(167,139,250,0.4)' : '#a78bfa'};text-decoration:none;" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">Ver vídeo ↗</a>` : ''}
                            ${badge}
                        </div>
                    </label>
                </div>`;
        }

        function renderPvsItems(groups) {
            const list = document.getElementById('pvs-list');
            list.innerHTML = '';
            groups.forEach((group, gi) => {
                const cid     = `pvs-group-${gi}`;
                const itemsHtml = group.items.map((item, ii) => renderPvsItem(item, group.variable_id, ii)).join('');
                const li      = document.createElement('li');
                li.className  = 'list-group-item px-0 py-0';
                li.style.borderBottom = '1px solid rgba(255,255,255,0.08)';
                li.innerHTML  = `
                    <div class="d-flex align-items-center gap-2 py-3">
                        <button class="d-flex align-items-center gap-2 flex-grow-1 p-0" style="background:none;border:none;cursor:pointer;text-align:left;min-width:0;" onclick="togglePvsCollapse('${cid}', this)">
                            <svg id="${cid}-icon" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" stroke-width="2.5" stroke="#a78bfa" fill="none" style="transition:transform .2s;flex-shrink:0;transform:${gi===0?'rotate(180deg)':'rotate(0deg)'}"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M6 9l6 6l6 -6"/></svg>
                            <span class="fw-semibold" style="font-size:0.88rem;color:#c4b5fd;">${group.label}</span>
                            <span class="badge bg-purple-lt ms-1" style="font-size:0.68rem;">${group.items.length}</span>
                        </button>
                        <div class="d-flex gap-1 flex-shrink-0">
                            <button onclick="sortPvsGroup(${gi},'plays',this)" id="${cid}-sort-plays" style="font-size:0.68rem;padding:2px 8px;border-radius:10px;border:1px solid rgba(109,40,217,0.3);background:rgba(109,40,217,0.18);color:#a78bfa;cursor:pointer;font-weight:600;">↓ Views</button>
                            <button onclick="sortPvsGroup(${gi},'recent',this)" id="${cid}-sort-recent" style="font-size:0.68rem;padding:2px 8px;border-radius:10px;border:1px solid rgba(255,255,255,0.1);background:transparent;color:rgba(255,255,255,0.4);cursor:pointer;font-weight:600;">Mais recente</button>
                        </div>
                    </div>
                    <div id="${cid}" style="display:${gi===0?'block':'none'};padding-bottom:4px;">
                        <div id="${cid}-items">${itemsHtml}</div>
                    </div>`;
                list.appendChild(li);
            });
        }

        function togglePvsCollapse(id, btn) {
            const el = document.getElementById(id), icon = document.getElementById(id + '-icon');
            const open = el.style.display === 'none';
            el.style.display = open ? 'block' : 'none';
            icon.style.transform = open ? 'rotate(180deg)' : '';
        }

        function sortPvsGroup(gi, sortType, clickedBtn) {
            const group = _pvsItems[gi], cid = `pvs-group-${gi}`;
            const container = document.getElementById(`${cid}-items`);
            if (!container || !group) return;
            const aS = 'font-size:0.68rem;padding:2px 8px;border-radius:10px;border:1px solid rgba(109,40,217,0.3);background:rgba(109,40,217,0.18);color:#a78bfa;cursor:pointer;font-weight:600;';
            const iS = 'font-size:0.68rem;padding:2px 8px;border-radius:10px;border:1px solid rgba(255,255,255,0.1);background:transparent;color:rgba(255,255,255,0.4);cursor:pointer;font-weight:600;';
            document.getElementById(`${cid}-sort-plays`).style.cssText  = sortType === 'plays'  ? aS : iS;
            document.getElementById(`${cid}-sort-recent`).style.cssText = sortType === 'recent' ? aS : iS;
            const sorted = [...group.items].sort((a, b) => sortType === 'plays' ? (parseInt(b.plays)||0) - (parseInt(a.plays)||0) : (b.result_id||0) - (a.result_id||0));
            container.innerHTML = sorted.map((item, ii) => renderPvsItem(item, group.variable_id, ii)).join('');
        }

        function selectAllPvsItems(btn) {
            const boxes = Array.from(document.querySelectorAll('#pvs-list .pvs-checkbox:not(:disabled)'));
            const allChecked = boxes.every(c => c.checked);
            boxes.forEach(c => { c.checked = !allChecked; onPvsCheckboxChange(c); });
            document.getElementById('pvs-select-all-label').textContent = allChecked ? 'Selecionar todos' : 'Desmarcar todos';
        }

        function onPvsCheckboxChange(el) {
            el.checked ? _pvsSelectedKeys.add(el.dataset.key) : _pvsSelectedKeys.delete(el.dataset.key);
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
            const orig = btn.innerHTML;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span> Salvando...';
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
                if (data.success) {
                    toastr.success(data.message);
                    btn.style.display = 'none';
                    _pvsSelectedKeys.clear();
                    // pvs-selected-count vive dentro do botão e é recriado pelo finally (btn.innerHTML = orig);
                    // por isso pode estar ausente aqui — acessos null-safe evitam quebrar a limpeza dos itens.
                    const selCount = document.getElementById('pvs-selected-count');
                    if (selCount) selCount.textContent = '0';
                    const selAllLabel = document.getElementById('pvs-select-all-label');
                    if (selAllLabel) selAllLabel.textContent = 'Selecionar todos';
                    checkboxes.forEach(el => {
                        try {
                            const row = el.closest('[data-pvs-row]');
                            el.checked = false; el.disabled = true;
                            el.style.cssText += ';opacity:0.4;cursor:not-allowed;';
                            if (!row) return;
                            row.style.opacity = '0.55';
                            const title = row.querySelector('.pvs-item-title');
                            if (title) { title.style.textDecoration = 'line-through'; title.style.color = 'rgba(255,255,255,0.35)'; }
                            const meta = row.querySelector('.pvs-item-meta');
                            if (meta && !meta.querySelector('.pvs-added-badge')) {
                                const badge = document.createElement('span');
                                badge.className = 'pvs-added-badge';
                                badge.style.cssText = 'font-size:0.68rem;color:rgba(255,255,255,0.4);display:flex;align-items:center;gap:3px;';
                                badge.textContent = '✓ Já adicionado';
                                meta.appendChild(badge);
                            }
                        } catch {}
                    });
                } else {
                    toastr.warning(data.message || 'Erro ao salvar.');
                }
            } catch (e) {
                console.error(e);
                toastr.error('Erro ao salvar variáveis. Tente novamente.');
            } finally {
                // Sempre restaura o estado do botão (nunca fica preso em "Salvando...").
                // No sucesso ele fica com display:none; ao selecionar um novo item o
                // onPvsCheckboxChange o reexibe já habilitado e com o rótulo original.
                btn.disabled = false;
                btn.innerHTML = orig;
            }
        }
    