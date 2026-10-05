/**
 * Advanced Roadmap Modal - Biblioteca de Vídeos Virais
 *
 * Gerencia a seleção de vídeos virais da biblioteca para usar como referência
 * na criação de roteiros avançados
 */

// Objeto global para gerenciar a biblioteca
window.AdvancedRoadmapLibrary = {
    selectedVideo: null,
    videos: [],
    filters: {
        search: '',
        format: '',
        profile: '',
        views_min: '',
        likes_min: '',
        niche: ''
    },
    filtersVisible: false,

    /**
     * Abre a biblioteca de vídeos virais
     */
    async open() {
        console.log('[Library] Abrindo biblioteca de vídeos virais');

        // Resetar estado dos filtros (garantir que estejam escondidos)
        this.filtersVisible = false;
        const panel = document.getElementById('libraryFiltersPanel');
        const button = document.getElementById('filterButtonText');
        if (panel) {
            panel.style.display = 'none';
        }
        if (button) {
            button.textContent = 'Mostrar Filtros';
        }

        // Fazer fade out do formulário
        const formState = document.getElementById('advancedRoadmapFormState');
        formState.classList.add('fade-out');

        setTimeout(() => {
            formState.style.display = 'none';

            // Mostrar estado da biblioteca
            const libraryState = document.getElementById('advancedRoadmapLibraryState');
            libraryState.style.display = 'block';
            libraryState.classList.add('fade-in');

            // Carregar vídeos
            this.loadVideos();

            // Adicionar listener para Enter no campo de busca
            setTimeout(() => {
                const searchField = document.getElementById('filterSearch');
                if (searchField) {
                    searchField.addEventListener('keypress', (e) => {
                        if (e.key === 'Enter') {
                            this.applyFilters();
                        }
                    });
                }

                // Inicializar TomSelect para o filtro de perfil (seleção única com busca)
                this.initProfileTomSelect();
            }, 400);
        }, 300);
    },

    /**
     * Esconde o painel de filtros
     */
    hideFilters() {
        this.filtersVisible = false;
        const panel = document.getElementById('libraryFiltersPanel');
        const button = document.getElementById('filterButtonText');

        if (panel) {
            panel.style.display = 'none';
        }
        if (button) {
            button.textContent = 'Mostrar Filtros';
        }

        console.log('[Library] Filtros escondidos');
    },

    /**
     * Reseta o estado da biblioteca (esconde biblioteca e mostra formulário)
     */
    resetState() {
        console.log('[Library] Resetando estado da biblioteca');

        // Esconder filtros
        this.hideFilters();

        // Esconder estado da biblioteca
        const libraryState = document.getElementById('advancedRoadmapLibraryState');
        if (libraryState) {
            libraryState.style.display = 'none';
            libraryState.classList.remove('fade-in');
            libraryState.classList.remove('fade-out');
        }

        // Mostrar estado do formulário
        const formState = document.getElementById('advancedRoadmapFormState');
        if (formState) {
            formState.style.display = 'block';
            formState.classList.remove('fade-out');
            formState.classList.remove('fade-in');
        }

        console.log('[Library] Estado resetado');
    },

    /**
     * Fecha a biblioteca e volta ao formulário
     */
    close() {
        console.log('[Library] Fechando biblioteca');

        // Esconder filtros ao fechar
        this.hideFilters();

        const libraryState = document.getElementById('advancedRoadmapLibraryState');
        libraryState.classList.add('fade-out');

        setTimeout(() => {
            libraryState.style.display = 'none';
            libraryState.classList.remove('fade-in');

            // Mostrar formulário novamente
            const formState = document.getElementById('advancedRoadmapFormState');
            formState.style.display = 'block';
            formState.classList.remove('fade-out');
            formState.classList.add('fade-in');
        }, 300);
    },

    /**
     * Carrega vídeos da biblioteca via AJAX
     */
    async loadVideos() {
        console.log('[Library] Carregando vídeos da biblioteca', this.filters);

        const loadingState = document.getElementById('libraryLoadingState');
        const gridState = document.getElementById('libraryVideosGrid');

        loadingState.style.display = 'block';
        gridState.style.display = 'none';

        try {
            // Construir query string com filtros
            const params = new URLSearchParams();

            if (this.filters.search) {
                params.append('transcription_search', this.filters.search);
            }
            if (this.filters.format) {
                params.append('format_video', this.filters.format);
            }
            if (this.filters.profile) {
                params.append('profile', this.filters.profile);
            }
            if (this.filters.views_min) {
                params.append('views_min', this.filters.views_min);
            }
            if (this.filters.likes_min) {
                params.append('likes_min', this.filters.likes_min);
            }
            if (this.filters.niche) {
                params.append('niche', this.filters.niche);
            }

            const queryString = params.toString();
            const url = '/dashboard/user/library/videos' + (queryString ? '?' + queryString : '');

            console.log('[Library] URL da requisição:', url);

            // Fazer requisição AJAX para buscar vídeos (rota Laravel)
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error('Erro ao carregar vídeos');
            }

            const data = await response.json();
            this.videos = data.videos || [];

            console.log('[Library] Vídeos carregados:', this.videos.length);

            // Renderizar grid de vídeos
            this.renderVideos();

            // Atualizar contador de resultados
            this.updateResultsCount(this.videos.length);

            // Esconder loading e mostrar grid
            loadingState.style.display = 'none';
            gridState.style.display = 'block';

        } catch (error) {
            console.error('[Library] Erro ao carregar vídeos:', error);

            loadingState.innerHTML = `
                <div class="alert alert-danger">
                    [SVG]
                    Erro ao carregar vídeos da biblioteca. Tente novamente.
                </div>
                <button class="btn btn-primary" onclick="AdvancedRoadmapLibrary.loadVideos()">
                    Tentar Novamente
                </button>
            `;
        }
    },

    /**
     * Renderiza o grid de vídeos
     */
    renderVideos() {
        const container = document.getElementById('viralVideosContainer');

        if (this.videos.length === 0) {
            // Verificar se há filtros ativos
            const hasActiveFilters = Object.values(this.filters).some(v => v !== '');

            const message = hasActiveFilters
                ? 'Nenhum vídeo encontrado com estes filtros. Tente ajustar os critérios.'
                : 'Nenhum vídeo viral encontrado na biblioteca.';

            container.innerHTML = `
                <div class="col-12">
                    <div class="text-center py-5">
                        [SVG]
                        <h5 class="text-muted mb-2">${message}</h5>
                        ${hasActiveFilters ? `
                            <button class="btn btn-sm btn-outline-primary mt-2" onclick="AdvancedRoadmapLibrary.clearFilters()">
                                [SVG]
                                Limpar Filtros
                            </button>
                        ` : ''}
                    </div>
                </div>
            `;
            return;
        }

        let html = '';

        this.videos.forEach(video => {
            const isSelected = this.selectedVideo && this.selectedVideo.id === video.id;
            const selectedClass = isSelected ? 'selected' : '';
            const snippetData = this.filters.search ? this.getSnippetForVideo(video, this.filters.search) : null;

            // Formatar números
            const plays = this.formatNumber(video.plays || 0);
            const likes = this.formatNumber(video.likes || 0);
            const comments = this.formatNumber(video.comments || 0);

            // Título truncado
            const title = video.title || video.description || 'Vídeo viral';
            const truncatedTitle = title.length > 60 ? title.substring(0, 60) + '...' : title;
            const avatarTitle = this.getSafeAvatarText(title);

            // Thumbnail ou placeholder com gradiente e ícone
            const thumbnail = video.thumbnail_url || `https://ui-avatars.com/api/?name=${avatarTitle}&size=400&background=ae3ec9&color=fff&bold=true`;

            html += `
                <div class="col-md-4 col-sm-6">
                    <div class="card viral-video-card ${selectedClass}" onclick="AdvancedRoadmapLibrary.selectVideo(${video.id})">
                        <!-- Badge de Check -->
                        <div class="check-badge">
                            [SVG]
                        </div>

                        <!-- Thumbnail -->
                        <img src="${thumbnail}" class="viral-video-thumbnail" alt="${truncatedTitle}" onerror="this.src='https://ui-avatars.com/api/?name=${avatarTitle}&size=400&background=gray&color=fff&bold=true'">

                        <div class="card-body">
                            <h6 class="card-title mb-2" title="${title}">${truncatedTitle}</h6>

                            <!-- Estatísticas -->
                            <div class="d-flex justify-content-between text-muted small mb-2">
                                <span title="Visualizações">
                                    [SVG]
                                    ${plays}
                                </span>
                                <span title="Curtidas">
                                    [SVG]
                                    ${likes}
                                </span>
                                <span title="Comentários">
                                    [SVG]
                                    ${comments}
                                </span>
                            </div>

                            ${snippetData ? `
                                <div class="search-snippet mt-2">
                                    <span class="snippet-label">${snippetData.source}</span>
                                    <div class="snippet-text">${snippetData.content}</div>
                                </div>
                            ` : ''}

                            <!-- Formato do vídeo (se disponível) -->
                            ${video.format_name ? `
                                <div class="mt-2">
                                    <span class="badge bg-purple-lt">${video.format_name}</span>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
    },

    /**
     * Gera texto seguro para uso em URLs de avatar
     */
    getSafeAvatarText(text) {
        if (!text) {
            return 'Video';
        }

        try {
            const normalized = Array.from(text).slice(0, 60).join('').trim();
            return encodeURIComponent(normalized || 'Video');
        } catch (error) {
            console.warn('[Library] Falha ao gerar placeholder de avatar, utilizando fallback.', error);
            const sanitized = (text || 'Video').replace(/[\p{Cs}]/gu, '').slice(0, 30) || 'Video';
            return encodeURIComponent(sanitized);
        }
    },

    /**
     * Seleciona um vídeo
     */
    selectVideo(videoId) {
        console.log('[Library] Selecionando vídeo:', videoId);

        // Buscar vídeo no array
        const video = this.videos.find(v => v.id === videoId);

        if (!video) {
            console.error('[Library] Vídeo não encontrado:', videoId);
            return;
        }

        this.selectedVideo = video;

        // Atualizar UI (hidden + grid)
        this.updateSelectedVideoUI();

        // Fechar biblioteca e voltar ao formulário; mostrar badge só depois do form estar visível
        setTimeout(() => {
            this.close();
            setTimeout(() => {
                this.showSelectedVideoBadge();
                const badge = document.getElementById('selectedVideoBadge');
                const section = document.getElementById('roadmapVideoModelSection');
                if (badge && section) {
                    section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            }, 350);
        }, 500);
    },

    /**
     * Atualiza a UI do vídeo selecionado no grid
     */
    updateSelectedVideoUI() {
        // Remover classe 'selected' de todos os cards
        document.querySelectorAll('.viral-video-card').forEach(card => {
            card.classList.remove('selected');
        });

        // Adicionar classe 'selected' ao card selecionado
        if (this.selectedVideo) {
            const selectedCard = document.querySelector(`.viral-video-card[onclick*="${this.selectedVideo.id}"]`);
            if (selectedCard) {
                selectedCard.classList.add('selected');
            }

            const hiddenField = document.getElementById('selectedViralVideoId');
            if (hiddenField) {
                hiddenField.value = this.selectedVideo.id;
                console.log('[Library] ✅ ID salvo no campo hidden:', { video_id: this.selectedVideo.id, field_value: hiddenField.value });
            }
        }
    },

    /**
     * Mostra o badge com informações do vídeo selecionado
     */
    showSelectedVideoBadge() {
        if (!this.selectedVideo) return;

        const badge = document.getElementById('selectedVideoBadge');
        const titleSpan = document.getElementById('selectedVideoTitle');
        const statsSpan = document.getElementById('selectedVideoStats');
        if (!badge || !titleSpan || !statsSpan) return;

        const title = this.selectedVideo.title || this.selectedVideo.description || 'Vídeo selecionado';
        const truncatedTitle = title.length > 50 ? title.substring(0, 50) + '...' : title;

        titleSpan.textContent = truncatedTitle;
        titleSpan.title = title;

        const plays = this.formatNumber(this.selectedVideo.plays || 0);
        const likes = this.formatNumber(this.selectedVideo.likes || 0);

        statsSpan.textContent = `${plays} views • ${likes} likes`;

        badge.style.setProperty('display', 'flex', 'important');
        badge.classList.remove('d-none');
        badge.classList.add('d-flex');
    },

    /**
     * Remove a seleção do vídeo
     */
    clearSelectedVideo() {
        console.log('[Library] Removendo seleção de vídeo');

        this.selectedVideo = null;

        const hidden = document.getElementById('selectedViralVideoId');
        if (hidden) hidden.value = '';

        const badge = document.getElementById('selectedVideoBadge');
        if (badge) {
            badge.style.setProperty('display', 'none', 'important');
            badge.classList.add('d-none');
            badge.classList.remove('d-flex');
        }
    },

    /**
     * Formata números grandes (1000 -> 1k)
     */
    formatNumber(num) {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'k';
        }
        return num.toString();
    },

    /**
     * Mostrar/esconder painel de filtros
     */
    toggleFilters() {
        this.filtersVisible = !this.filtersVisible;

        const panel = document.getElementById('libraryFiltersPanel');
        const button = document.getElementById('filterButtonText');

        if (this.filtersVisible) {
            panel.style.display = 'block';
            button.textContent = 'Esconder Filtros';
        } else {
            panel.style.display = 'none';
            button.textContent = 'Mostrar Filtros';
        }
    },

    /**
     * Aplicar filtros e recarregar vídeos
     */
    applyFilters() {
        console.log('[Library] Aplicando filtros');

        // Ler valores dos campos
        this.filters.search = document.getElementById('filterSearch').value.trim();
        this.filters.format = document.getElementById('filterFormat').value;

        // Obter valor do perfil do TomSelect ou do campo direto
        const profileField = document.getElementById('filterProfile');
        if (window.libraryProfileSelect && window.libraryProfileSelect.getValue) {
            const profileValue = window.libraryProfileSelect.getValue();
            this.filters.profile = Array.isArray(profileValue) ? profileValue[0] : profileValue;
        } else {
            this.filters.profile = profileField ? profileField.value : '';
        }

        this.filters.views_min = document.getElementById('filterViews').value;
        this.filters.likes_min = document.getElementById('filterLikes').value;
        this.filters.niche = document.getElementById('filterNiche').value;

        console.log('[Library] Filtros aplicados:', this.filters);

        // Atualizar contador de filtros ativos
        this.updateActiveFiltersCount();

        // Recarregar vídeos com os novos filtros
        this.loadVideos();
    },

    /**
     * Limpar todos os filtros
     */
    clearFilters() {
        console.log('[Library] Limpando filtros');

        // Resetar objeto de filtros
        this.filters = {
            search: '',
            format: '',
            profile: '',
            views_min: '',
            likes_min: '',
            niche: ''
        };

        // Resetar campos do formulário
        document.getElementById('filterSearch').value = '';
        document.getElementById('filterFormat').value = '';

        // Limpar TomSelect do perfil se estiver inicializado
        const profileField = document.getElementById('filterProfile');
        if (window.libraryProfileSelect && window.libraryProfileSelect.clear) {
            window.libraryProfileSelect.clear();
        } else if (profileField) {
            profileField.value = '';
        }

        document.getElementById('filterViews').value = '';
        document.getElementById('filterLikes').value = '';
        document.getElementById('filterNiche').value = '';

        // Atualizar contador
        this.updateActiveFiltersCount();

        // Recarregar vídeos sem filtros
        this.loadVideos();
    },

    /**
     * Atualizar contador de filtros ativos
     */
    updateActiveFiltersCount() {
        let count = 0;

        if (this.filters.search) count++;
        if (this.filters.format) count++;
        if (this.filters.profile) count++;
        if (this.filters.views_min) count++;
        if (this.filters.likes_min) count++;
        if (this.filters.niche) count++;

        const badge = document.getElementById('activeFiltersCount');
        const clearBtn = document.getElementById('clearLibraryFilters');

        if (count > 0) {
            badge.textContent = count;
            badge.style.display = 'inline-block';
            clearBtn.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
            clearBtn.style.display = 'none';
        }

        console.log('[Library] Filtros ativos:', count);
    },

    /**
     * Atualizar contador de resultados encontrados
     */
    updateResultsCount(count) {
        const counterElement = document.getElementById('libraryResultsCount');
        if (counterElement) {
            counterElement.textContent = count;
        }
    },

    /**
     * Gera um snippet com destaque para o termo buscado
     */
    getSnippetForVideo(video, searchTerms) {
        if (!searchTerms) {
            return null;
        }

        // Busca no título
            const titleSnippet = this.extractHighlightedSnippet(video.title, searchTerms, 0, 'Título');
        if (titleSnippet) {
            return titleSnippet;
        }

        // Busca na transcrição com contexto
        if (video.transcription_text) {
            const transcriptionSnippet = this.extractHighlightedSnippet(video.transcription_text, searchTerms, 120, 'Trecho da transcrição');
            if (transcriptionSnippet) {
                return transcriptionSnippet;
            }
        }

        return null;
    },

    extractHighlightedSnippet(text, searchTerms, contextLength = 0, label = 'Trecho') {
        if (!text) {
            return null;
        }

        const snippet = contextLength > 0
            ? this.extractSnippet(text, searchTerms, contextLength)
            : this.highlightSearchTerms(text, searchTerms);

        if (!snippet) {
            return null;
        }

        return {
            source: label,
            content: snippet
        };
    },

    extractSnippet(text, searchTerms, contextLength = 100) {
        if (!text || !searchTerms) {
            return null;
        }

        const normalizedText = this.removeAccents(text).toLowerCase();
        const terms = searchTerms.split(',').map(term => term.trim()).filter(Boolean);

        for (const term of terms) {
            const normalizedTerm = this.removeAccents(term).toLowerCase();
            if (!normalizedTerm) {
                continue;
            }

            const index = normalizedText.indexOf(normalizedTerm);
            if (index !== -1) {
                const start = Math.max(0, index - contextLength);
                const end = Math.min(text.length, index + term.length + contextLength);

                let snippet = text.substring(start, end);
                if (start > 0) {
                    snippet = '…' + snippet;
                }
                if (end < text.length) {
                    snippet = snippet + '…';
                }

                return this.highlightSearchTerms(snippet, searchTerms);
            }
        }

        return null;
    },

    highlightSearchTerms(text, searchTerms) {
        if (!text || !searchTerms) {
            return text;
        }

        let highlightedText = text;
        const terms = searchTerms.split(',').map(term => term.trim()).filter(Boolean);

        terms.forEach(term => {
            if (!term) {
                return;
            }

            const escapedTerm = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            const regex = new RegExp(escapedTerm, 'gi');
            highlightedText = highlightedText.replace(regex, match => `<mark class="highlight-match">${match}</mark>`);
        });

        return highlightedText;
    },

    removeAccents(value) {
        if (!value) {
            return '';
        }

        return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    },

    /**
     * Inicializa o TomSelect para o filtro de perfil (seleção única com busca)
     */
    initProfileTomSelect() {
        const profileField = document.getElementById('filterProfile');

        if (!profileField) {
            console.log('[Library] Campo filterProfile não encontrado');
            return;
        }

        // Verificar se TomSelect já foi inicializado
        if (profileField.tomselect) {
            console.log('[Library] TomSelect já inicializado para filterProfile');
            return;
        }

        // Verificar se TomSelect está disponível
        if (typeof TomSelect === 'undefined') {
            console.warn('[Library] TomSelect não está disponível. Certifique-se de que a biblioteca está carregada.');
            return;
        }

        console.log('[Library] Inicializando TomSelect para filterProfile');

        // Inicializar TomSelect com configuração idêntica à rota library
        window.libraryProfileSelect = new TomSelect('#filterProfile', {
            copyClassesToDropdown: false,
            dropdownParent: 'body',
            create: false,
            placeholder: 'Selecione um perfil...',
            allowEmptyOption: true,
            maxItems: 1, // Limitar a 1 seleção
            render: {
                option: function(data, escape) {
                    return `<div class="option">${escape(data.text)}</div>`;
                }
            },
            onChange: (value) => {
                console.log('[Library] Perfil selecionado:', value);
                // Aplicar filtros automaticamente quando o perfil mudar
                this.applyFilters();
            }
        });

        console.log('[Library] ✅ TomSelect inicializado para filterProfile');
    }
};

// Disponibilizar globalmente
window.AdvancedRoadmapLibrary = AdvancedRoadmapLibrary;

