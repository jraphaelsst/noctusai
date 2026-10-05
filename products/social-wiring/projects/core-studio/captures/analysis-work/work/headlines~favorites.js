/* ===== SCRIPT #1 @27091 attrs= len=794 */

        (function() {
            // ✅ V2 SEMPRE USA TEMA DARK (forçado como padrão)
            // CÓDIGO ANTERIOR (comentado - respeitava localStorage):
            // const theme = localStorage.getItem('tablerTheme');
            // if (!theme) {
            //     localStorage.setItem('tablerTheme', 'dark');
            //     document.documentElement.classList.add('theme-dark');
            // } else if (theme === 'dark') {
            //     document.documentElement.classList.add('theme-dark');
            // }

            // NOVO CÓDIGO: Força dark sempre na v2
            localStorage.setItem('tablerTheme', 'dark');
            document.documentElement.classList.add('theme-dark');
            document.documentElement.setAttribute('data-bs-theme', 'dark');
        })();
    
/* ===== SCRIPT #3 @28033 attrs= len=469 */

        // ✅ V2 SEMPRE USA TEMA DARK (forçado após demo-theme.min.js)
        // Garante que o dark seja aplicado mesmo se o demo-theme.min.js tentar aplicar light
        (function() {
            localStorage.setItem('tablerTheme', 'dark');
            document.documentElement.classList.add('theme-dark');
            document.documentElement.setAttribute('data-bs-theme', 'dark');
            document.body.setAttribute('data-bs-theme', 'dark');
        })();
    
/* ===== SCRIPT #4 @59834 attrs= len=232 */

    const btn = document.querySelector('#btnShowMenuV2');
    const menuDropdown = document.querySelector('.dropdownMenuProfileV2');

    btn.addEventListener('click', () => {
        menuDropdown.classList.toggle('upV2');
    });

/* ===== SCRIPT #5 @75367 attrs= len=3598 */

function creditsBadge() {
    return {
        balance: null,

        init() {
            this.fetch();
            setInterval(() => this.fetch(), 30000);
        },

        async fetch() {
            try {
                const res = await fetch('https://corestudio.ai/dashboard/user/twin/api/credits', {
                    headers: { Accept: 'application/json' },
                });

                if (!res.ok) return;

                const json = await res.json();
                this.balance = json.balance;
                this.$el.classList.toggle('is-empty', json.balance < json.cost_per_minute);
            } catch (e) {
                console.error('[CreditsBadge] Erro ao buscar saldo:', e);
            }
        },
    };
}

function notificationsDropdown() {
    return {
        open: false,
        showRead: false,
        notifications: [],
        unreadCount: 0,
        readCount: 0,

        init() {
            this.fetch();
            setInterval(() => this.fetch(), 30000);
        },

        toggle() {
            this.open = !this.open;
            if (this.open) this.fetch();
        },

        toggleShowRead() {
            this.showRead = !this.showRead;
            this.fetch();
        },

        async fetch() {
            try {
                const url = new URL('https://corestudio.ai/dashboard/user/notifications', window.location.origin);
                if (this.showRead) url.searchParams.set('show_read', '1');
                const res = await fetch(url, {
                    headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
                });
                const data = await res.json();
                this.notifications = data.notifications;
                this.unreadCount = data.unread_count;
                this.readCount = data.read_count;
            } catch (e) {
                console.error('[Notifications] Erro ao buscar:', e);
            }
        },

        async markRead(n) {
            if (n.status === 1) return;
            n.status = 1;
            this.unreadCount = Math.max(0, this.unreadCount - 1);
            this.readCount++;
            const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            await fetch(`/dashboard/user/notifications/${n.id}/read`, {
                method: 'POST',
                headers: { 'X-CSRF-TOKEN': token, 'Accept': 'application/json' }
            });
        },

        async markAllRead() {
            this.readCount += this.notifications.filter(n => n.status === 0).length;
            this.notifications = this.showRead
                ? this.notifications.map(n => ({ ...n, status: 1 }))
                : [];
            this.unreadCount = 0;
            const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            await fetch('https://corestudio.ai/dashboard/user/notifications/read-all', {
                method: 'POST',
                headers: { 'X-CSRF-TOKEN': token, 'Accept': 'application/json' }
            });
        },

        timeAgo(dateStr) {
            const now = new Date();
            const date = new Date(dateStr);
            const diff = Math.floor((now - date) / 1000);
            if (diff < 60) return 'agora';
            if (diff < 3600) return Math.floor(diff / 60) + ' min atrás';
            if (diff < 86400) return Math.floor(diff / 3600) + 'h atrás';
            if (diff < 604800) return Math.floor(diff / 86400) + 'd atrás';
            return date.toLocaleDateString('pt-BR');
        }
    }
}

/* ===== SCRIPT #6 @245896 attrs= len=1958 */

                                    document.addEventListener("DOMContentLoaded", function() {
                                        var el;
                                        window.TomSelect && (new TomSelect(el = document.getElementById(
                                            'make-headlines-select-3'), {
                                            copyClassesToDropdown: false,
                                            dropdownParent: 'body',
                                            controlInput: '<input>',
                                            render: {
                                                item: function(data, escape) {
                                                    if (data.customProperties) {
                                                        return '<div><span class="dropdown-item-indicator">' + data
                                                            .customProperties + '</span>' + escape(data.text) + '</div>';
                                                    }
                                                    return '<div>' + escape(data.text) + '</div>';
                                                },
                                                option: function(data, escape) {
                                                    if (data.customProperties) {
                                                        return '<div><span class="dropdown-item-indicator">' + data
                                                            .customProperties + '</span>' + escape(data.text) + '</div>';
                                                    }
                                                    return '<div>' + escape(data.text) + '</div>';
                                                },
                                            },
                                        }));
                                    });
                                
/* ===== SCRIPT #7 @249930 attrs= len=1958 */

                                    document.addEventListener("DOMContentLoaded", function() {
                                        var el;
                                        window.TomSelect && (new TomSelect(el = document.getElementById(
                                            'make-headlines-select-4'), {
                                            copyClassesToDropdown: false,
                                            dropdownParent: 'body',
                                            controlInput: '<input>',
                                            render: {
                                                item: function(data, escape) {
                                                    if (data.customProperties) {
                                                        return '<div><span class="dropdown-item-indicator">' + data
                                                            .customProperties + '</span>' + escape(data.text) + '</div>';
                                                    }
                                                    return '<div>' + escape(data.text) + '</div>';
                                                },
                                                option: function(data, escape) {
                                                    if (data.customProperties) {
                                                        return '<div><span class="dropdown-item-indicator">' + data
                                                            .customProperties + '</span>' + escape(data.text) + '</div>';
                                                    }
                                                    return '<div>' + escape(data.text) + '</div>';
                                                },
                                            },
                                        }));
                                    });
                                
/* ===== SCRIPT #8 @254076 attrs= len=1958 */

                                    document.addEventListener("DOMContentLoaded", function() {
                                        var el;
                                        window.TomSelect && (new TomSelect(el = document.getElementById(
                                            'make-headlines-select-7'), {
                                            copyClassesToDropdown: false,
                                            dropdownParent: 'body',
                                            controlInput: '<input>',
                                            render: {
                                                item: function(data, escape) {
                                                    if (data.customProperties) {
                                                        return '<div><span class="dropdown-item-indicator">' + data
                                                            .customProperties + '</span>' + escape(data.text) + '</div>';
                                                    }
                                                    return '<div>' + escape(data.text) + '</div>';
                                                },
                                                option: function(data, escape) {
                                                    if (data.customProperties) {
                                                        return '<div><span class="dropdown-item-indicator">' + data
                                                            .customProperties + '</span>' + escape(data.text) + '</div>';
                                                    }
                                                    return '<div>' + escape(data.text) + '</div>';
                                                },
                                            },
                                        }));
                                    });
                                
/* ===== SCRIPT #16 @311146 attrs= len=1020 */

    $.ajaxSetup({
        headers: {
            'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content')
        }
    });

    // Interceptador global para erros de CSRF
    $(document).ajaxError(function(event, jqXHR, settings, thrownError) {
        if (jqXHR.status === 419 || // Laravel CSRF token expirado
            (jqXHR.responseJSON && 
            jqXHR.responseJSON.message && 
            jqXHR.responseJSON.message.toLowerCase().includes('csrf'))) {
            
            toastr.error('Sua sessão expirou. A página será recarregada.');
            
            // Recarrega a página após 2 segundos
            setTimeout(function() {
                window.location.reload();
            }, 2000);
        }
    });

    // Adiciona interceptador para renovar token CSRF periodicamente
    setInterval(function() {
        $.get('/csrf-token', function(data) {
            $('meta[name="csrf-token"]').attr('content', data.token);
        });
    }, 30 * 60 * 1000); // Renova a cada 30 minutos

/* ===== SCRIPT #18 @312276 attrs= len=1372 */

    // Configuração das rotas para o componente
    window.AdvancedRoadmapModalConfig = {
        routes: {
            generateQuestions: "https://corestudio.ai/dashboard/user/headlines/favorites/advanced-roadmap/generate-questions",
            store: "https://corestudio.ai/dashboard/user/headlines/favorites/advanced-roadmap/store",
            show: "https://corestudio.ai/dashboard/user/headlines/favorites/advanced-roadmap/show/__ID__",
            chat: "https://corestudio.ai/dashboard/user/chat/__ID__",
            updateRoadmap: "https://corestudio.ai/dashboard/user/roadmaps/update",
            updateSuggested: "https://corestudio.ai/dashboard/user/headlines/suggested/update",
            updateFavorites: "https://corestudio.ai/dashboard/user/headlines/favorites/update",
            listSearch: "https://corestudio.ai/dashboard/user/headlines/suggested/advanced-roadmap/list-search",
            directSearch: "https://corestudio.ai/dashboard/user/headlines/suggested/advanced-roadmap/direct-search",
            translateSearchQuery: "https://corestudio.ai/dashboard/user/headlines/suggested/advanced-roadmap/translate-search-query",
            translateSearchResults: "https://corestudio.ai/dashboard/user/headlines/suggested/advanced-roadmap/translate-search-results"
        },
        csrfToken: "HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC"
    };


/* ===== SCRIPT #26 @314359 attrs= len=6306 */

        // Override para popular aba de fontes no modal de edição
        $(document).ready(function() {
            // Interceptar o evento de abrir modal de edição para buscar fontes
            $('#modal-edit-headline-favorite').on('shown.bs.modal', function() {
                // Sempre ativar a aba "Roteiro" ao abrir o modal
                setTimeout(function() {
                    // Remover active de todas as abas
                    $('#modal-edit-headline-favorite .nav-link').removeClass('active');
                    $('#modal-edit-headline-favorite .tab-pane').removeClass('active show');

                    // Ativar a aba "Roteiro"
                    var $roteiroTab = $('#edit-roadmap-tab');
                    var $roteiroPane = $('#edit-roadmap-content');

                    if ($roteiroTab.length && $roteiroPane.length) {
                        $roteiroTab.addClass('active');
                        $roteiroPane.addClass('active show');

                        // Usar Bootstrap Tab API para garantir ativação
                        var tab = new bootstrap.Tab($roteiroTab[0]);
                        tab.show();
                    }
                }, 50);

                // Esperar um pouco para garantir que o AJAX do headlines.js já terminou
                setTimeout(function() {
                    const headlineId = $('form#headline-favorite-edit').find('input[name="id"]')
                        .val();
                    $('form#headline-favorite-edit')
                        .data('chat-resource-id', headlineId)
                        .data('chat-resource-type', 'eng_reversa_headlines');

                    if (headlineId) {
                        // Buscar dados completos incluindo search_text
                        $.ajax({
                            url: '/dashboard/user/roadmaps/favorites/show-favorites',
                            type: 'POST',
                            data: {
                                _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                                id: headlineId
                            },
                            success: function(data) {
                                // Verificar se há search_text para mostrar a aba de fontes
                                if (data.success && data.search_text && data.search_text.trim() !== '') {
                                    console.log(
                                        'Dados de pesquisa encontrados para modal de edição'
                                    );
                                    // Mostrar a aba de fontes
                                    $('#edit-sources-tab-li').show();

                                    // Formatar e exibir o search_text
                                    let searchTextFormatted = data.search_text.replace(
                                        /\n/g, '<br>');
                                    $('#edit-search-sources-content').html(
                                        searchTextFormatted);
                                } else {
                                    // Esconder a aba de fontes
                                    $('#edit-sources-tab-li').hide();
                                    $('#edit-search-sources-content').html('');
                                }
                            },
                            error: function(xhr) {
                                // Esconder a aba em caso de erro
                                $('#edit-sources-tab-li').hide();
                                $('#edit-search-sources-content').html('');
                            }
                        });
                    }
                }, 800); // Delay para garantir que o headlines.js já carregou os dados
            });

            // Limpar dados ao fechar o modal
            $('#modal-edit-headline-favorite').on('hidden.bs.modal', function() {
                $('#edit-sources-tab-li').hide();
                $('#edit-search-sources-content').html('');
            });

            $('#start_chat_favorite').on('click', function(e) {
                e.preventDefault();
                const resourceId = $('form#headline-favorite-edit').data('chat-resource-id');
                const resourceType = $('form#headline-favorite-edit').data('chat-resource-type');
                window.startChatMode(resourceId, resourceType, this);
            });

            if (typeof window.startChatMode !== 'function') {
                window.startChatMode = function(resourceId, resourceType, buttonElement) {
                    if (!resourceId || !resourceType) {
                        toastr.error('Roteiro não encontrado para iniciar o modo chat.');
                        return;
                    }

                    const $button = $(buttonElement);
                    $button.prop('disabled', true);

                    $.ajax({
                        url: '/dashboard/user/chat/start',
                        method: 'POST',
                        data: {
                            _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                            resource_id: resourceId,
                            resource_type: resourceType
                        },
                        success: function(response) {
                            if (response.success && response.redirect) {
                                window.location.href = response.redirect;
                            } else {
                                toastr.error(response.message ||
                                    'Não foi possível iniciar o modo chat.');
                            }
                        },
                        error: function(xhr) {
                            let message = 'Não foi possível iniciar o modo chat.';
                            if (xhr.responseJSON && xhr.responseJSON.message) {
                                message = xhr.responseJSON.message;
                            }
                            toastr.error(message);
                        },
                        complete: function() {
                            $button.prop('disabled', false);
                        }
                    });
                };
            }
        });
    
/* ===== SCRIPT #27 @320688 attrs= len=23474 */

        // @formatter:off
        document.addEventListener("DOMContentLoaded", function() {
            window.noUiSlider && (noUiSlider.create(document.getElementById('range-simple'), {
                start: 5,
                connect: [true, false],
                step: 1,
                range: {
                    min: 0,
                    max: 10
                }
            }));
        });
        // @formatter:on

        $(document).ready(function() {
            let customSearchInput = null
            const params = new URLSearchParams(window.location.search);
            $('#customSearchInput').on('input', function() {
                customSearchInput = null;
                const url = new URL(window.location.href);
                url.searchParams.delete('hid');
                window.history.replaceState({}, '', url);
            })

            const headline_id = params.get('hid');
            if(headline_id) {
                customSearchInput = "#headline_id:" + headline_id
            }

            var table = new DataTable('#myFavorites', {
                responsive: true,
                searchDelay: 500,
                processing: true,
                serverSide: true,
                lengthChange: false,
                searching: false,
                pagingType: "simple_numbers",
                ajax: {
                    url: "/dashboard/user/headlines/favorites/list",
                    type: 'POST',

                    data: function(d) {
                        d.search = {
                            value:  customSearchInput ?? $('#customSearchInput').val(), // O valor do input de pesquisa
                            regex: false // Não estamos utilizando regex
                        };
                    },
                    error: function(xhr, error, thrown) {
                        console.log('Erro na requisição:', error);
                        return false;
                    }
                },
                columns: [{
                        data: 'Checkbox',
                        orderable: false,
                        searchable: false
                    },
                    {
                        data: 'ID'
                    },
                    {
                        data: 'User'
                    },
                    {
                        data: 'Headline'
                    },
                    {
                        data: 'Actions',
                        responsivePriority: -1
                    },
                ],
                columnDefs: [{
                        targets: 0,
                        render: (data, type, row) => {
                            return `<input type="checkbox" class="form-check-input favorite-checkbox" value="${row.ID}" data-favorite-id="${ row.ID }">`;
                        },
                        orderable: false,
                        searchable: false
                    },
                    {
                        // The `data` parameter refers to the data for the cell (defined by the
                        // `data` option, which defaults to the column being worked with, in
                        // this case `data: 0`.
                        targets: 1,
                        render: (data, type, row) => `<span >${ data }</span>`
                    },
                    {
                        targets: 2,
                        render: (data, type, row) => {
                            return `
                                <td data-label="Name">
                                    <div class="d-flex py-1 align-items-center">
                                        <div class="flex-fill">
                                            <div >
                                                ${ row.Data }
                                            </div>
                                        </div>
                                    </div>
                                </td>
                            `
                        }
                    },
                    {
                        targets: 3,
                        orderable: false,
                        render: (data, type, row) => {
                            var roadmapBadge = row.Roadmap ? '<span class="badge bg-primary text-white me-2">Roteiro criado</span>' : '';
                            return `
                                <td data-label="Variable"
                                    <div class="d-flex py-1 align-items-center">
                                        <div class="flex-fill">
                                            <div class="font-weight-medium">
                                                ${row.Headline }
                                            </div>
                                            <div class="text-secondary mt-2">
                                                ${roadmapBadge}
                                            </div>
                                        </div>
                                    </div>
                                </td>
                            `
                        }
                    },
                    {
                        render: function(data, type, row) {
                            var roadmapButton = '';
                            if (1 == 0) {
                                var roadmapButton = `
                                    <a href="javascript:;" onclick="getQuestions(${row.HeadlineId })"
                                        style="width: 40px !important; height: 40px !important; padding: 0 !important;"
                                        data-headline="${ encodeURIComponent(row.Headline) }" id="${ row.ID }"
                                        class="btn btn-outline-blue rounded-circle w-100 btn-icon j_headlines_favorites_make_roadmap"
                                        data-headline-id="${row.HeadlineId }" data-structure-id="${ row.Structure }">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
                                            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                                                class="icon icon-tabler icons-tabler-outline icon-tabler-checklist">
                                                <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
                                                <path d="M9.615 20h-2.615a2 2 0 0 1 -2 -2v-12a2 2 0 0 1 2 -2h8a2 2 0 0 1 2 2v8"></path>
                                                <path d="M14 19l2 2l4 -4"></path>
                                                <path d="M9 8h4"></path>
                                                <path d="M9 12h2"></path>
                                        </svg>
                                    </a>
                                `;

                                if (row.EngReversaFlowResult) {

                                    var roadmapButton = `
                                        <a href="javascript:;" data-headline="${encodeURIComponent(row.Headline)}" id="${row.ID }"
                                            style="width: 40px !important; height: 40px !important; padding: 0 !important;"
                                            class="rounded-circle btn btn-outline-blue w-100 btn-icon j_headlines_favorites_make_roadmap_new"
                                            data-headline-id="${row.HeadlineId}" data-structure-id="${row.Structure}">
                                            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
                                                fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
                                                stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-checklist">
                                                <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
                                                <path d="M9.615 20h-2.615a2 2 0 0 1 -2 -2v-12a2 2 0 0 1 2 -2h8a2 2 0 0 1 2 2v8"></path>
                                                <path d="M14 19l2 2l4 -4"></path>
                                                <path d="M9 8h4"></path>
                                                <path d="M9 12h2"></path>
                                            </svg>
                                        </a>
                                    `;
                                }
                            }
                            // Botão de link viral - só aparece se EngReversaResultId não for null
                            var viralButton = '';
                            if (row.EngReversaResultId) {
                                viralButton = `
                                    <a href="/dashboard/user/library?viral_id=${row.EngReversaResultId}" target="_blank"
                                        style="width: 40px !important; height: 40px !important; padding: 0 !important;"
                                        class="rounded-circle btn btn-outline-green w-100 btn-icon" title="Ver Viral na Biblioteca">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
                                            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                                            class="icon icon-tabler icons-tabler-outline icon-tabler-video">
                                            <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                            <path d="M15 10l4.553 -2.276a1 1 0 0 1 1.447 .894v6.764a1 1 0 0 1 -1.447 .894l-4.553 -2.276v-4z" />
                                            <path d="M3 6m0 2a2 2 0 0 1 2 -2h8a2 2 0 0 1 2 2v8a2 2 0 0 1 -2 2h-8a2 2 0 0 1 -2 -2z" />
                                        </svg>
                                    </a>
                                `;
                            }

                            // Botão de roteiro avançado (só para usuários com permissão)
                            var advancedButton = '';
                            advancedButton = `
                                <a href="javascript:;" data-headline="${encodeURIComponent(row.Headline)}" id="${row.ID}"
                                    style="width: 40px !important; height: 40px !important; padding: 0 !important;"
                                    class="rounded-circle btn btn-outline-purple w-100 btn-icon j_headlines_favorites_advanced_roadmap"
                                    data-headline-id="${row.ID}" title="Roteiro Avançado">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
                                        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                                        class="icon icon-tabler icons-tabler-outline icon-tabler-wand">
                                        <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                        <path d="M6 21l15 -15l-3 -3l-15 15l3 3" />
                                        <path d="M15 6l3 3" />
                                        <path d="M9 3a2 2 0 0 0 2 2a2 2 0 0 0 -2 2a2 2 0 0 0 -2 -2a2 2 0 0 0 2 -2" />
                                        <path d="M19 13a2 2 0 0 0 2 2a2 2 0 0 0 -2 2a2 2 0 0 0 -2 -2a2 2 0 0 0 2 -2" />
                                    </svg>
                                </a>
                            `;

                            return `
                                <div class="btn-list flex-nowrap">
                                    <a href="javascript:;" id="${row.ID}" class="rounded-circle btn btn-outline-blue w-100 btn-icon j_headlines_favorites_edit"
                                        style="width: 40px !important; height: 40px !important; padding: 0 !important;"
                                        data-headline-id="${row.HeadlineId}" data-structure-id="${row.Structure }"
                                        data-headline="${encodeURIComponent(row.Headline) }" >
                                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
                                            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                                            class="icon icon-tabler icons-tabler-outline icon-tabler-edit">
                                            <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                            <path d="M7 7h-1a2 2 0 0 0 -2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2 -2v-1" />
                                            <path d="M20.385 6.585a2.1 2.1 0 0 0 -2.97 -2.97l-8.415 8.385v3h3l8.385 -8.415z" />
                                            <path d="M16 5l3 3" />
                                        </svg>
                                    </a>
                                    ${roadmapButton} ${viralButton } ${ advancedButton }
                                    <a href="javascript:;" id="${row.ID } "
                                        class="rounded-circle btn btn-outline-danger w-100 btn-icon j_headlines_favorites_delete"
                                        style="width: 40px !important; height: 40px !important; padding: 0 !important;"
                                        data-headline-id="${row.HeadlineId}" data-headline="${row.Headline}">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
                                            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                                            class="icon icon-tabler icons-tabler-outline icon-tabler-trash">
                                            <path stroke="none" d="M0 0h24v24H0z" fill="none"/>
                                            <path d="M4 7l16 0" />
                                            <path d="M10 11l0 6" />
                                            <path d="M14 11l0 6" />
                                            <path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12" />
                                            <path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3" />
                                        </svg>
                                    </a>
                                </div>
                            `;
                        },
                        orderable: false,
                        targets: 4
                    },
                ],
                language: {
                    "lengthMenu": "Mostrar _MENU_ registros por página",
                    "zeroRecords": "Nenhum resultado encontrado",
                    "info": "Mostrando _START_ a _END_ de _TOTAL_ registros",
                    "infoEmpty": "Mostrando 0 a 0 de 0 registros",
                    "infoFiltered": "(filtrado de _MAX_ registros no total)",
                    "search": "Buscar:",
                    "paginate": {
                        "first": "Primeiro",
                        "last": "Último",
                        "next":  `
                            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
                                fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
                                stroke-linejoin="round" class="lucide lucide-chevron-right-icon lucide-chevron-right">
                                <path d="m9 18 6-6-6-6"/>
                            </svg>
                        `,
                        "previous": `
                            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
                                fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
                                stroke-linejoin="round" class="lucide lucide-chevron-left-icon lucide-chevron-left">
                                <path d="m15 18-6-6 6-6"/>
                            </svg>
                        `
                    },
                    "loadingRecords": "Carregando...",
                    "processing": "Processando...",
                    "infoThousands": ".",
                    "decimal": ","
                }
            });

            // Recarregar a tabela ao digitar no campo de pesquisa personalizado
            $('#customSearchInput').on('keyup', function() {
                table.ajax.reload();
            });

            // Gerenciar seleção de todos os checkboxes
            $('#select-all-favorites').on('change', function() {
                var isChecked = $(this).prop('checked');
                $('.favorite-checkbox').prop('checked', isChecked);
                toggleDeleteButtonFavorites();
            });

            // Gerenciar seleção individual de checkboxes
            $(document).on('change', '.favorite-checkbox', function() {
                var totalCheckboxes = $('.favorite-checkbox').length;
                var checkedCheckboxes = $('.favorite-checkbox:checked').length;

                $('#select-all-favorites').prop('checked', totalCheckboxes === checkedCheckboxes);
                toggleDeleteButtonFavorites();
            });

            // Função para mostrar/ocultar botão de exclusão em massa
            function toggleDeleteButtonFavorites() {
                var checkedCount = $('.favorite-checkbox:checked').length;
                if (checkedCount > 0) {
                    $('#btn-delete-multiple-favorites').show();
                    $('#btn-delete-multiple-favorites').html(
                        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon me-2"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M4 7l16 0"></path><path d="M10 11l0 6"></path><path d="M14 11l0 6"></path><path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12"></path><path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3"></path></svg>Excluir Selecionados (' +
                        checkedCount + ')');
                } else {
                    $('#btn-delete-multiple-favorites').hide();
                }
            }

            // Exclusão em massa
            $('#btn-delete-multiple-favorites').on('click', function() {
                var selectedIds = [];
                $('.favorite-checkbox:checked').each(function() {
                    selectedIds.push($(this).val());
                });

                if (selectedIds.length === 0) {
                    toastr.warning('Selecione pelo menos uma headline para excluir.');
                    return;
                }

                // Atualizar mensagem do modal
                var message = selectedIds.length === 1 ?
                    'Você realmente deseja deletar esta headline?' :
                    'Você realmente deseja deletar ' + selectedIds.length + ' headline(s) selecionada(s)?';
                $('#modal-favorites-delete-multiple-message').text(message);

                // Armazenar IDs selecionados para uso no confirm
                $('#modal-favorites-delete-multiple').data('selected-ids', selectedIds);

                // Abrir modal de confirmação
                $('#modal-favorites-delete-multiple').modal('show');
            });

            // Confirmar exclusão em massa
            $('#j_favorites_delete_multiple_confirm').on('click', function() {
                var selectedIds = $('#modal-favorites-delete-multiple').data('selected-ids');

                if (!selectedIds || selectedIds.length === 0) {
                    toastr.warning('Nenhuma headline selecionada.');
                    $('#modal-favorites-delete-multiple').modal('hide');
                    return;
                }

                var $button = $('#btn-delete-multiple-favorites');
                $button.prop('disabled', true);
                $button.html('<span class="spinner-border spinner-border-sm me-2"></span>Excluindo...');

                // Fechar modal
                $('#modal-favorites-delete-multiple').modal('hide');

                $.ajax({
                    url: '/dashboard/user/headlines/favorites/delete-multiple',
                    type: 'POST',
                    data: {
                        ids: selectedIds,
                        _token: $('meta[name="csrf-token"]').attr('content')
                    },
                    success: function(response) {
                        if (response.success) {
                            toastr.success(response.message);
                            // Desmarcar todos os checkboxes
                            $('.favorite-checkbox').prop('checked', false);
                            $('#select-all-favorites').prop('checked', false);
                            toggleDeleteButtonFavorites();

                            // Recarregar a tabela
                            if (response.refresh) {
                                setTimeout(function() {
                                    table.ajax.reload();
                                }, 500);
                            }
                        } else {
                            toastr.error(response.message || 'Erro ao excluir headlines.');
                        }
                    },
                    error: function(xhr) {
                        var message = 'Erro ao excluir headlines.';
                        if (xhr.responseJSON && xhr.responseJSON.message) {
                            message = xhr.responseJSON.message;
                        } else if (xhr.responseJSON && xhr.responseJSON.errors) {
                            var errors = xhr.responseJSON.errors;
                            message = Object.values(errors).flat().join(', ');
                        }
                        toastr.error(message);
                    },
                    complete: function() {
                        $button.prop('disabled', false);
                        $button.html(
                            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon me-2"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M4 7l16 0"></path><path d="M10 11l0 6"></path><path d="M14 11l0 6"></path><path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12"></path><path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3"></path></svg>Excluir Selecionados'
                        );
                    }
                });
            });

            // Resetar checkboxes quando a tabela for recarregada
            table.on('draw', function() {
                $('#select-all-favorites').prop('checked', false);
                toggleDeleteButtonFavorites();
            });
        });
    
/* ===== SCRIPT #28 @344185 attrs= len=520 */

        document.addEventListener('DOMContentLoaded', function() {
            const tx = document.getElementsByClassName('auto-resize');
            for (let i = 0; i < tx.length; i++) {
                tx[i].setAttribute('style', 'resize: none; overflow: hidden;');
                tx[i].addEventListener("input", OnInput, false);
            }

            function OnInput() {
                this.style.height = 'auto';
                this.style.height = (this.scrollHeight) + 'px';
            }
        });
    
/* ===== SCRIPT #29 @344728 attrs= len=17546 */

        // Funções para o modal de roteiro novo
        function createRoadmapNew(headlineId) {
            console.log('Criar roteiro para headline:', headlineId);
            document.getElementById('roadmapContentNew').value = '';

            // Buscar a headline no DOM - usando o botão que foi clicado (ID do elemento)
            const clickedButton = document.getElementById(headlineId);
            const headlineText = clickedButton.getAttribute('data-headline');

            // Preencher o modal
            document.getElementById('roadmapHeadlineNew').value = decodeURIComponent(headlineText);
            document.getElementById('roadmapHeadlineIdNew').value = headlineId;

            // Mostrar estado inicial (formulário)
            showRoadmapStateNew('form');

            // Abrir o modal
            const modal = new bootstrap.Modal(document.getElementById('createRoadmapModalNew'));
            modal.show();
        }

        function showRoadmapStateNew(state) {
            // Esconder todos os estados
            document.getElementById('creatingRoadmapStateNew').style.display = 'none';
            document.getElementById('createRoadmapFormStateNew').style.display = 'none';
            document.getElementById('roadmapCreatedStateNew').style.display = 'none';

            // Mostrar o estado solicitado
            switch (state) {
                case 'creating':
                    document.getElementById('creatingRoadmapStateNew').style.display = 'block';
                    document.getElementById('createRoadmapBtnNew').style.display = 'none';
                    break;
                case 'form':
                    document.getElementById('createRoadmapFormStateNew').style.display = 'block';
                    document.getElementById('createRoadmapBtnNew').style.display = 'inline-block';
                    break;
                case 'result':
                    document.getElementById('roadmapCreatedStateNew').style.display = 'block';
                    document.getElementById('createRoadmapBtnNew').style.display = 'none';
                    break;
            }
        }

        function saveRoadmapNew() {
            const headlineId = document.getElementById('roadmapHeadlineIdNew').value;
            const roadmapContent = document.getElementById('roadmapContentNew').value.trim();

            if (!roadmapContent) {
                toastr.error('Por favor, preencha as observações adicionais');
                return;
            }

            // Mostrar estado de criação
            showRoadmapStateNew('creating');

            // AJAX para criar roteiro no backend
            $.ajax({
                url: "dashboard/user/roadmaps/favorites/store",
                type: 'POST',
                data: {
                    _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                    headline_id: headlineId,
                    observations: roadmapContent
                },
                success: function(data) {
                    if (data.success) {
                        // Iniciar long polling para verificar status
                        startLongPollingNew(headlineId);
                    } else {
                        // Voltar para o formulário em caso de erro
                        showRoadmapStateNew('form');
                        toastr.error(data.message || 'Erro ao criar o roteiro');
                    }
                },
                error: function(xhr) {
                    // Voltar para o formulário em caso de erro
                    showRoadmapStateNew('form');
                    toastr.error('Erro ao criar o roteiro');
                    console.error(xhr);
                }
            });
        }

        // Variável global para controlar o polling
        let pollingTimeout = null;
        let isPollingActive = false;

        function startLongPollingNew(headlineId) {
            let pollCount = 0;
            const maxPolls = 60; // Máximo 5 minutos (60 * 5 segundos)
            isPollingActive = true;

            function pollStatus() {
                // Verificar se o polling ainda está ativo
                if (!isPollingActive) {
                    return;
                }
                pollCount += randomNumber(1, 8);

                function randomNumber(min, max) {
                    return Math.floor(Math.random() * (max - min + 1)) + min;
                }

                // Atualizar progresso visual
                updateProgressNew(pollCount, maxPolls);

                $.ajax({
                    url: "dashboard/user/roadmaps/favorites/show-favorites",
                    type: 'POST',
                    data: {
                        _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                        id: headlineId
                    },
                    success: function(data) {
                        if (data.success && data.roadmap_engreversa && data.roadmap_engreversa !==
                            'Roteiro não disponível') {
                            // Roteiro está pronto!
                            document.getElementById('roadmapHeadlineResultNew').value = document.getElementById(
                                'roadmapHeadlineNew').value;
                            document.getElementById('roadmapResultNew').value = data.roadmap_engreversa;

                            // Mostrar estado de resultado
                            showRoadmapStateNew('result');

                            toastr.success('Roteiro criado com sucesso!');
                        } else if (pollCount >= maxPolls) {
                            // Timeout - parar polling
                            showRoadmapStateNew('form');
                            toastr.error(
                                'Timeout: O roteiro está demorando mais que o esperado. Tente novamente.');
                        } else {
                            // Continuar polling em 5 segundos
                            pollingTimeout = setTimeout(pollStatus, 5000);
                        }
                    },
                    error: function(xhr) {
                        if (pollCount >= maxPolls) {
                            isPollingActive = false;
                            showRoadmapStateNew('form');
                            toastr.error('Erro ao verificar status do roteiro');
                        } else {
                            // Continuar polling mesmo com erro
                            pollingTimeout = setTimeout(pollStatus, 5000);
                        }
                    }
                });
            }

            // Iniciar polling após 2 segundos
            pollingTimeout = setTimeout(pollStatus, 2000);
        }

        function stopPollingNew() {
            isPollingActive = false;
            if (pollingTimeout) {
                clearTimeout(pollingTimeout);
                pollingTimeout = null;
            }
        }

        function cancelRoadmapCreation() {
            // Parar polling
            stopPollingNew();

            // Voltar para o formulário
            showRoadmapStateNew('form');

            // Mostrar mensagem
            toastr.info('Criação de roteiro cancelada');
        }

        function updateProgressNew(current, max) {
            const progress = Math.min((current / max) * 100, 95); // Máximo 95% até estar pronto

            // Atualizar texto de progresso
            const progressText = document.querySelector('#creatingRoadmapStateNew h6');
            if (progressText) {
                progressText.textContent = `Criando seu roteiro... (${Math.round(progress)}%)`;
            }

            // Atualizar barra de progresso
            const progressBar = document.querySelector('#creatingRoadmapStateNew .progress-bar');
            if (progressBar) {
                progressBar.style.width = progress + '%';
                progressBar.setAttribute('aria-valuenow', progress);
            }

            // Atualizar status detalhado
            const statusElement = document.getElementById('progressStatus');
            if (statusElement) {
                let statusText = '';
                if (progress < 20) {
                    statusText = 'Enviando dados para processamento...';
                } else if (progress < 40) {
                    statusText = 'Analisando engenharia reversa...';
                } else if (progress < 60) {
                    statusText = 'Gerando roteiro personalizado...';
                } else if (progress < 80) {
                    statusText = 'Revisando e formatando conteúdo...';
                } else {
                    statusText = 'Finalizando roteiro...';
                }
                statusElement.textContent = statusText;
            }
        }

        function copyRoadmapNew() {
            const roadmapText = document.getElementById('roadmapResultNew').value;

            if (navigator.clipboard) {
                navigator.clipboard.writeText(roadmapText).then(function() {
                    toastr.success('Roteiro copiado para a área de transferência!');
                }).catch(function() {
                    fallbackCopyTextToClipboard(roadmapText);
                });
            } else {
                fallbackCopyTextToClipboard(roadmapText);
            }
        }

        function fallbackCopyTextToClipboard(text) {
            const textArea = document.createElement('textarea');
            textArea.value = text;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();

            try {
                document.execCommand('copy');
                toastr.success('Roteiro copiado para a área de transferência!');
            } catch (err) {
                toastr.error('Erro ao copiar o roteiro');
                console.error('Fallback: Oops, unable to copy', err);
            }

            document.body.removeChild(textArea);
        }

        function viewRoadmapNew(headlineId) {
            // Buscar a headline no DOM - usando o ID do elemento
            const clickedButton = document.getElementById(headlineId);
            const headlineText = clickedButton.getAttribute('data-headline');

            // Preencher a headline no modal
            document.getElementById('viewRoadmapHeadlineNew').value = decodeURIComponent(headlineText);

            // Buscar o roteiro via AJAX
            $.ajax({
                url: "dashboard/user/roadmaps/favorites/show-favorites",
                type: 'POST',
                data: {
                    _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                    id: headlineId
                },
                success: function(data) {
                    if (data.success) {
                        // Preencher o roteiro no modal
                        document.getElementById('viewRoadmapContentNew').value = data.roadmap_engreversa ||
                            'Roteiro não encontrado';

                        // Verificar se há search_text para mostrar a aba de fontes
                        if (data.search_text && data.search_text.trim() !== '') {
                            console.log('Dados de pesquisa encontrados no roteiro - viewRoadmapNew');
                            // Mostrar a aba de fontes
                            document.getElementById('view-sources-tab-li').style.display = 'block';

                            // Formatar e exibir o search_text
                            let searchTextFormatted = data.search_text.replace(/\n/g, '<br>');
                            document.getElementById('view-search-sources-content').innerHTML =
                                searchTextFormatted;
                        } else {
                            // Esconder a aba de fontes se não houver dados
                            document.getElementById('view-sources-tab-li').style.display = 'none';
                            document.getElementById('view-search-sources-content').innerHTML = '';
                        }

                        // Abrir o modal
                        const modal = new bootstrap.Modal(document.getElementById('viewRoadmapModalNew'));
                        modal.show();
                    } else {
                        toastr.error(data.message || 'Erro ao buscar o roteiro');
                    }
                },
                error: function(xhr) {
                    toastr.error('Erro ao buscar o roteiro');
                    console.error(xhr);
                }
            });
        }

        function copyViewRoadmapNew() {
            const roadmapText = document.getElementById('viewRoadmapContentNew').value;

            if (navigator.clipboard) {
                navigator.clipboard.writeText(roadmapText).then(function() {
                    toastr.success('Roteiro copiado para a área de transferência!');
                }).catch(function() {
                    fallbackCopyTextToClipboard(roadmapText);
                });
            } else {
                fallbackCopyTextToClipboard(roadmapText);
            }
        }

        // Event listener para parar polling quando modal for fechado
        document.addEventListener('hidden.bs.modal', function(e) {
            if (e.target.id === 'createRoadmapModalNew') {
                stopPollingNew();
            }
        });

        // Event delegation para os botões de ação novos
        document.addEventListener('click', function(e) {
            if (e.target.closest('.j_headlines_favorites_make_roadmap_new')) {
                e.preventDefault();
                const button = e.target.closest('.j_headlines_favorites_make_roadmap_new');
                const headlineId = button.id; // Usar o ID do elemento (primary key do registro)
                const headlineText = button.getAttribute('data-headline');

                if (headlineId && headlineId !== 'null' && headlineId !== 'undefined') {
                    // Verificar se já existe roteiro
                    checkExistingRoadmapNew(headlineId, headlineText);
                } else {
                    console.error('headlineId não encontrado no botão ou é null/undefined');
                }
            }
        });

        function checkExistingRoadmapNew(headlineId, headlineText) {
            // Buscar se já existe roteiro
            $.ajax({
                url: "dashboard/user/roadmaps/favorites/show-favorites",
                type: 'POST',
                data: {
                    _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                    id: headlineId
                },
                success: function(data) {
                    if (data.success && data.roadmap_engreversa) {
                        // Roteiro já existe - mostrar modal com o roteiro existente
                        showExistingRoadmapNew(headlineId, headlineText, data.roadmap_engreversa, data
                            .search_id, data.search_text);
                    } else {
                        // Roteiro não existe - criar novo
                        createRoadmapNew(headlineId);
                    }
                },
                error: function(xhr) {
                    // Em caso de erro, tentar criar novo roteiro
                    createRoadmapNew(headlineId);
                }
            });
        }

        function showExistingRoadmapNew(headlineId, headlineText, roadmapContent, searchId, searchText) {
            // Preencher o modal de visualização com o roteiro existente
            document.getElementById('viewRoadmapHeadlineNew').value = decodeURIComponent(headlineText);
            document.getElementById('viewRoadmapContentNew').value = roadmapContent;

            // Verificar se há dados de pesquisa para mostrar a aba de fontes
            if (searchId && searchText) {
                console.log('Dados de pesquisa encontrados no roteiro favorito');
                // Mostrar a aba de fontes
                document.getElementById('view-sources-tab-li').style.display = 'block';

                // Formatar e exibir o search_text
                let searchTextFormatted = searchText.replace(/\n/g, '<br>');
                document.getElementById('view-search-sources-content').innerHTML = searchTextFormatted;
            } else {
                // Esconder a aba de fontes se não houver dados
                document.getElementById('view-sources-tab-li').style.display = 'none';
                document.getElementById('view-search-sources-content').innerHTML = '';
            }

            // Abrir o modal de visualização
            const modal = new bootstrap.Modal(document.getElementById('viewRoadmapModalNew'));
            modal.show();
        }

        function recreateRoadmapNew() {
            const headlineId = document.getElementById('roadmapHeadlineIdNew').value;
            const headlineText = document.getElementById('roadmapHeadlineResultNew').value;

            // Limpar o campo de observações
            document.getElementById('roadmapContentNew').value = '';

            // Preencher o modal para recriação
            document.getElementById('roadmapHeadlineNew').value = headlineText;

            // Mostrar estado de formulário para recriar
            showRoadmapStateNew('form');
        }
    
/* ===== SCRIPT #30 @362302 attrs= len=799 */

        // Event listener para abrir modal de roteiro avançado (usando componente)
        document.addEventListener('click', function(e) {
            if (e.target.closest('.j_headlines_favorites_advanced_roadmap')) {
                e.preventDefault();
                const button = e.target.closest('.j_headlines_favorites_advanced_roadmap');
                const headlineId = button.getAttribute('data-headline-id');
                const headlineText = button.getAttribute('data-headline');

                if (headlineId && headlineId !== 'null' && headlineId !== 'undefined') {
                    AdvancedRoadmapModal.open(headlineId, headlineText);
                } else {
                    console.error('headlineId não encontrado');
                }
            }
        });
    
/* ===== SCRIPT #31 @363123 attrs= len=2677 */

        $('form#customers-workspace-create').submit(function(e) {
            "use strict";

            e.preventDefault();

            const getPath = () => location.pathname.startsWith('/dashboard/admin/team') ?
                "/dashboard/admin/team" :
                "/dashboard/admin/customers";

            const baseUrl = window.location.origin;


            $('#create_workspace').prop('disabled', true);
            $('#create_workspace').text('Aguarde criando...');

            var formData = new FormData(this);

            $.ajax({
                type: "post",
                url: baseUrl + getPath() + "/workspace/create",
                data: formData,
                contentType: false,
                processData: false,
                success: function(data) {
                    toastr[data.type](data.message);

                    if (data.refresh) {
                        setTimeout(function() {
                            window.location.reload();
                        }, 1000);
                    }
                },
                error: function(data) {
                    // Trata apenas erros não relacionados ao CSRF
                    if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message
                            .toLowerCase().includes('csrf'))) {
                        if (data.responseJSON && (data.responseJSON.error || data.responseJSON
                                .errors)) {
                            if (data.responseJSON.errors) {
                                var errors = data.responseJSON.errors;
                                $.each(errors, function(index, value) {
                                    toastr.error(value);
                                });
                            } else {
                                toastr.error(data.responseJSON.message);
                            }
                        } else {
                            toastr.error('Ocorreu um erro ao atualizar o cliente.');
                        }
                    }

                    $('#create_workspace').prop('disabled', false);
                    $('#create_workspace').html(
                        '<svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="none"  stroke="currentColor"  stroke-width="2"  stroke-linecap="round"  stroke-linejoin="round"  class="icon icon-tabler icons-tabler-outline icon-tabler-plus"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 5l0 14" /><path d="M5 12l14 0" /></svg>Criar'
                    );
                }
            });
            return false;
        })
    
/* ===== SCRIPT #33 @365893 attrs= len=605 */

    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;

    // Removido os eventos jQuery que controlavam a visibilidade dos botões
    // Agora isso é controlado pelo Alpine.js de forma reativa

    // Evento de clique no microfone agora é controlado pelo Alpine
    // $('.microphone-chat').click(function(){
    //     $('.audio-area-chat').removeClass('hidden');
    //     $('.input-message').addClass('hidden');
    //     $('.sendText').addClass('hidden');
    //     $('.microphone-chat').addClass('hidden');
    //     $("#record-button-chat").click();
    // });


/* ===== SCRIPT #34 @366517 attrs= len=9045 */

    let chatRecording = {
        isRecording: false,
        timer: null,
        seconds: 0,
        mediaRecorder: null,
        audioChunks: [],
        audioBlob: null,
        audioContext: null,
        analyser: null,
        dataArray: null
    };

    // Insere ícones SVG
    $(".icon-microphone-chat").html(`<svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="currentColor"  class="icon icon-tabler icons-tabler-filled icon-tabler-microphone"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M19 9a1 1 0 0 1 1 1a8 8 0 0 1 -6.999 7.938l-.001 2.062h3a1 1 0 0 1 0 2h-8a1 1 0 0 1 0 -2h3v-2.062a8 8 0 0 1 -7 -7.938a1 1 0 1 1 2 0a6 6 0 0 0 12 0a1 1 0 0 1 1 -1m-7 -8a4 4 0 0 1 4 4v5a4 4 0 1 1 -8 0v-5a4 4 0 0 1 4 -4" /></svg>`);
    $(".icon-pause-chat").html(`<svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="currentColor"  class="icon icon-tabler icons-tabler-filled icon-tabler-player-pause"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M9 4h-2a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h2a2 2 0 0 0 2 -2v-12a2 2 0 0 0 -2 -2z" /><path d="M17 4h-2a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h2a2 2 0 0 0 2 -2v-12a2 2 0 0 0 -2 -2z" /></svg>`);
    $(".icon-trash-chat").html(`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"  viewBox="0 0 24 24"  fill="none"  stroke="currentColor"  stroke-width="2"  stroke-linecap="round"  stroke-linejoin="round"  class="icon icon-tabler icons-tabler-outline icon-tabler-trash"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 7l16 0" /><path d="M10 11l0 6" /><path d="M14 11l0 6" /><path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12" /><path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3" /></svg>`);

    // Configura canvas
    function setupChatCanvas(canvas) {
        const scale = window.devicePixelRatio || 1;
        canvas.width = canvas.offsetWidth * scale;
        canvas.height = canvas.offsetHeight * scale;
        canvas.getContext("2d").scale(scale, scale);
    }

    // Clique no botão de gravação
    $("#record-button-chat").click(async () => {
        const canvas = document.getElementById("waveform-chat");
        const micIcon = $("#record-button-chat .mic-icon");
        const micPause = $("#record-button-chat .mic-pause");
        const timerEl = $("#record-timer-chat");
        const divAudio = $(".div-audio-chat");
        const divControls = $(".div-controls-chat");
        const player = $("#audio-player-chat");

        setupChatCanvas(canvas);

        if (!chatRecording.isRecording) {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                chatRecording.audioContext = new AudioContext();
                chatRecording.analyser = chatRecording.audioContext.createAnalyser();
                chatRecording.analyser.fftSize = 256;
                chatRecording.dataArray = new Uint8Array(chatRecording.analyser.frequencyBinCount);
                const source = chatRecording.audioContext.createMediaStreamSource(stream);
                source.connect(chatRecording.analyser);

                chatRecording.mediaRecorder = new MediaRecorder(stream, {
                    mimeType: 'audio/webm'
                });
                chatRecording.audioChunks = [];
                chatRecording.mediaRecorder.ondataavailable = e => chatRecording.audioChunks.push(e.data);
                chatRecording.mediaRecorder.start();

                chatRecording.seconds = 0;
                timerEl.text("00:00");
                chatRecording.timer = setInterval(() => {
                    chatRecording.seconds++;
                    timerEl.text(new Date(chatRecording.seconds * 1000).toISOString().substr(14, 5));
                }, 1000);

                micIcon.addClass("hidden");
                micPause.removeClass("hidden");
                chatRecording.isRecording = true;

                // animação canvas
                const ctx = canvas.getContext("2d");
                function draw() {
                    if (!chatRecording.isRecording) return;
                    chatRecording.analyser.getByteFrequencyData(chatRecording.dataArray);
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    let x = 0;
                    const barCount = 120;
                    const barWidth = Math.floor(canvas.width / barCount) - 2;
                    for (let i = 0; i < barCount; i++) {
                        const index = Math.floor((i / barCount) * chatRecording.dataArray.length);
                        const height = (chatRecording.dataArray[index] / 255) * canvas.height * 0.8;
                        ctx.fillStyle = "#00BFFF";
                        ctx.fillRect(x, (canvas.height - height) / 2, barWidth, height);
                        x += barWidth + 2;
                    }
                    requestAnimationFrame(draw);
                }
                draw();
            } catch (error) {
                alert("Erro ao acessar o microfone.");
                console.error(error);
            }
        } else {
            // Parar
            chatRecording.isRecording = false;
            micIcon.removeClass("hidden");
            micPause.addClass("hidden");
            clearInterval(chatRecording.timer);
            chatRecording.mediaRecorder.stop();

            chatRecording.mediaRecorder.onstop = () => {
                console.log('MediaRecorder parou');
                console.log('Audio chunks:', chatRecording.audioChunks.length);

                chatRecording.audioBlob = new Blob(chatRecording.audioChunks, { type: 'audio/webm' });
                console.log('Audio blob criado:', !!chatRecording.audioBlob);

                const url = URL.createObjectURL(chatRecording.audioBlob);
                console.log('URL criada:', url);

                player.attr("src", url);
                divAudio.addClass("hidden");
                divControls.removeClass("hidden");

                player[0].onloadedmetadata = () => {
                    if (player[0].duration === Infinity) {
                        player[0].currentTime = 1e101;
                        player[0].ontimeupdate = () => {
                            player[0].ontimeupdate = null;
                            player[0].currentTime = 0; // volta ao início
                        };
                    }
                };


                // Atualizar o estado do Alpine
                const alpineComponent = document.querySelector('[x-data="aiChat"]').__x;
                if (alpineComponent) {
                    // Forçar atualização do estado
                    alpineComponent.$data.audioUrl = url;
                    alpineComponent.$data.audioBlob = chatRecording.audioBlob;
                    alpineComponent.$data.isLoading = false;

                    // Debug
                    console.log('Audio Blob definido no Alpine:', !!alpineComponent.$data.audioBlob);
                    console.log('Audio URL definido no Alpine:', !!alpineComponent.$data.audioUrl);
                }

                // Garantir que chatRecording está acessível globalmente
                window.chatRecording = chatRecording;
                console.log('chatRecording definido globalmente:', !!window.chatRecording);
                console.log('chatRecording.audioBlob global:', !!window.chatRecording.audioBlob);
            };
        }
    });

    // Botão de apagar - agora controlado pelo Alpine.js
    // $("#delete-button-chat").click(() => {
    //     // Usar o Alpine.js para resetar os controles
    //     const alpineComponent = document.querySelector('[x-data="aiChat"]').__x;
    //     if (alpineComponent) {
    //         alpineComponent.switchToText();
    //     }
    //
    //     // Resetar elementos específicos do áudio
    //     $(".div-controls-chat").addClass("hidden");
    //     $(".div-audio-chat").removeClass("hidden");
    //     $("#record-timer-chat").text("00:00");
    //     $("#audio-player-chat").attr("src", "");

    //     // Resetar variáveis do chatRecording
    //     chatRecording = {
    //         isRecording: false,
    //         timer: null,
    //         seconds: 0,
    //         mediaRecorder: null,
    //         audioChunks: [],
    //         audioBlob: null,
    //         audioContext: null,
    //         analyser: null,
    //         dataArray: null
    //     };
    // });

    // Adicionar evento de clique no botão de enviar áudio
    $('.sendAudio').on('click', function() {
        const alpineComponent = document.querySelector('[x-data="aiChat"]').__x;
        if (alpineComponent && chatRecording.audioBlob) {
            // Garantir que o audioBlob está definido antes de chamar sendMessage
            alpineComponent.$data.audioBlob = chatRecording.audioBlob;
            alpineComponent.$data.audioUrl = URL.createObjectURL(chatRecording.audioBlob);
            alpineComponent.sendMessage();
        }
    });


/* ===== SCRIPT #35 @375589 attrs= len=1554 */

            $(document).ready(function() {
                const $dropdowns = $('.navDropdownV2');
                const $navLinks = $('.navLinkV2');
                const $dropdownBoxes = $('.asideDropdownItemV2');

                $dropdowns.on('click', function() {
                    // Remove estados ativos
                    // $dropdowns.removeClass('active');
                    // $navLinks.removeClass('active');
                    $dropdownBoxes.removeClass('d-block');

                    // Ativa o dropdown atual
                    const $current = $(this);
                    // $current.addClass('active');
                    $current.find('.asideDropdownItemV2').addClass('d-block');
                });

                $('.subMenuTriggerV2').on('click', function(e) {
                    e.stopPropagation();
                    $(this).closest('.subMenuV2').toggleClass('open');
                });

                const containerBodyAsideV2 = $(".containerBodyAsideV2")
                $('#toggleSidebarButtonV2').on('click', function() {
                    containerBodyAsideV2.slideToggle(300);
                })

                $(window).on('resize', function(e) {
                    if (window.innerWidth > 990) {
                        containerBodyAsideV2.show()
                        containerBodyAsideV2.css("display", "flex")
                    } else {
                        containerBodyAsideV2.hide()
                    }
                });

                
                            })
        
/* ===== SCRIPT #36 @381105 attrs= len=1479 */

        document.addEventListener('DOMContentLoaded', function() {
            var modalEl = document.getElementById('modal-first-access-tutorial');
            if (!modalEl) return;

            // O backdrop do Bootstrap é anexado ao body, fora do modal — a classe no body
            // limita o escurecimento/blur a este modal e preserva os demais da plataforma.
            modalEl.addEventListener('show.bs.modal', function() {
                document.body.classList.add('first-access-modal-open');
            });
            modalEl.addEventListener('hidden.bs.modal', function() {
                document.body.classList.remove('first-access-modal-open');
            });

            
            function markFirstAccessSeen() {
                var token = document.querySelector('meta[name="csrf-token"]');
                if (!token) return;
                fetch('https://corestudio.ai/dashboard/user/first-access-seen', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': token.getAttribute('content'), 'Accept': 'application/json' },
                    body: '{}'
                }).catch(function() {});
            }

            document.getElementById('btn-first-access-trainings').addEventListener('click', markFirstAccessSeen, { once: true });
            document.getElementById('btn-first-access-skip').addEventListener('click', markFirstAccessSeen, { once: true });
        });
    
/* ===== SCRIPT #37 @382607 attrs=data-navigate-once="true" len=137 */
window.livewireScriptConfig = {"csrf":"HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC","uri":"\/livewire\/update","progressBar":"","nonce":""};
/* ===== SCRIPT #41 @383028 attrs= len=4402 */

            (function configureEcho() {
                if (window.Echo && window.Echo.__advancedRoadmapConfigured) {
                    console.warn('[Echo] Já inicializado anteriormente, ignorando nova configuração.');
                    window.dispatchEvent(new CustomEvent('echo:ready'));
                    return;
                }

                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
                const userId = document.querySelector('meta[name="user-id"]')?.getAttribute('content');
                const env = document.querySelector('meta[name="app-env"]')?.getAttribute('content') || 'local';

                const pusherKey = "75830eeb9f5ab6e769a8";
                const pusherCluster = "us2";
                const configuredHost = "api-us2.pusher.com";
                const configuredPort = "443";
                const forceTLS = true;

                const isCustomHost = configuredHost && !configuredHost.startsWith('api-');
                const wsHost = isCustomHost ? configuredHost : null;
                const wsPort = isCustomHost && configuredPort ? Number(configuredPort) : null;
                const wssPort = isCustomHost && configuredPort ? Number(configuredPort) : null;

                if (!pusherKey || pusherKey === 'null') {
                    console.error('[AdvancedRoadmapChat] Pusher key não configurado. Verifique broadcasting.php.');
                    return;
                }

                console.info('[AdvancedRoadmapChat] Bootstrap do Echo', {
                    pusherKey,
                    pusherCluster,
                    wsHost,
                    wsPort,
                    wssPort,
                    forceTLS,
                    env,
                    userId,
                });

                const echoOptions = {
                    broadcaster: 'pusher',
                    key: pusherKey,
                    cluster: pusherCluster,
                    forceTLS: forceTLS,
                    enabledTransports: ['ws', 'wss'],
                    disableStats: true,
                    encrypted: forceTLS,
                    authEndpoint: '/broadcasting/auth',
                    auth: {
                        headers: {
                            'X-CSRF-TOKEN': csrfToken,
                        },
                    },
                };

                if (wsHost) {
                    echoOptions.wsHost = wsHost;
                }
                if (wsPort) {
                    echoOptions.wsPort = wsPort;
                }
                if (wssPort) {
                    echoOptions.wssPort = wssPort;
                }

                window.Echo = new Echo(echoOptions);
                window.Echo.__advancedRoadmapConfigured = true;
                window.dispatchEvent(new CustomEvent('echo:ready'));

                const pusher = window.Echo.connector?.pusher;
                if (!pusher) {
                    console.error('[AdvancedRoadmapChat] Falha ao obter instância do Pusher via Echo.');
                    return;
                }

                pusher.connection.bind('connecting', () => console.debug('[Echo] Conectando...'));
                pusher.connection.bind('connected', () => console.info('[Echo] Conectado com sucesso.'));
                pusher.connection.bind('disconnected', () => console.warn('[Echo] Desconectado.'));
                pusher.connection.bind('unavailable', () => console.warn('[Echo] Servidor indisponível.'));
                pusher.connection.bind('failed', () => console.error('[Echo] Conexão falhou.'));
                pusher.connection.bind('error', (error) => console.error('[Echo] Erro na conexão Pusher', error));

                if (console && console.debug) {
                    pusher.bind_global((eventName, data) => {
                        console.debug('[Echo] Evento global recebido', eventName, data);
                    });
                }

                window.addEventListener('beforeunload', () => {
                    try {
                        window.Echo.disconnect();
                        console.debug('[Echo] Conexão encerrada (beforeunload).');
                    } catch (error) {
                        console.error('[Echo] Erro ao desconectar', error);
                    }
                });
            })();
        
/* ===== SCRIPT #44 @387671 attrs=type="text/javascript" len=361 */

        window.$crisp = [];
        window.CRISP_WEBSITE_ID = "75cc752d-b49d-4b10-9a51-aeb70cf165c3";
                (function() {
            d = document;
            s = d.createElement("script");
            s.src = "https://client.crisp.chat/l.js";
            s.async = 1;
            d.getElementsByTagName("head")[0].appendChild(s);
        })();
    