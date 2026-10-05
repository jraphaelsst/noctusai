/* ===== SCRIPT #1 @27090 attrs= len=794 */

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
    
/* ===== SCRIPT #3 @28032 attrs= len=469 */

        // ✅ V2 SEMPRE USA TEMA DARK (forçado após demo-theme.min.js)
        // Garante que o dark seja aplicado mesmo se o demo-theme.min.js tentar aplicar light
        (function() {
            localStorage.setItem('tablerTheme', 'dark');
            document.documentElement.classList.add('theme-dark');
            document.documentElement.setAttribute('data-bs-theme', 'dark');
            document.body.setAttribute('data-bs-theme', 'dark');
        })();
    
/* ===== SCRIPT #4 @59833 attrs= len=232 */

    const btn = document.querySelector('#btnShowMenuV2');
    const menuDropdown = document.querySelector('.dropdownMenuProfileV2');

    btn.addEventListener('click', () => {
        menuDropdown.classList.toggle('upV2');
    });

/* ===== SCRIPT #5 @75366 attrs= len=3598 */

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

/* ===== SCRIPT #6 @243914 attrs= len=1958 */

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
                                
/* ===== SCRIPT #7 @247948 attrs= len=1958 */

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
                                
/* ===== SCRIPT #8 @252094 attrs= len=1958 */

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
                                
/* ===== SCRIPT #16 @308294 attrs= len=1020 */

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

/* ===== SCRIPT #18 @309424 attrs= len=1372 */

    // Configuração das rotas para o componente
    window.AdvancedRoadmapModalConfig = {
        routes: {
            generateQuestions: "https://corestudio.ai/dashboard/user/headlines/suggested/advanced-roadmap/generate-questions",
            store: "https://corestudio.ai/dashboard/user/headlines/suggested/advanced-roadmap/store",
            show: "https://corestudio.ai/dashboard/user/headlines/suggested/advanced-roadmap/show/__ID__",
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


/* ===== SCRIPT #25 @311416 attrs= len=21354 */

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
            // Função para formatar números (K para milhares, M para milhões)
            function formatNumber(num) {
                if (num >= 1000000) {
                    return (num / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
                } else if (num >= 1000) {
                    return (num / 1000).toFixed(1).replace(/\.0$/, '') + 'K';
                } else {
                    return num.toString();
                }
            }

            var table = new DataTable('#mySuggested', {
                responsive: true,
                searchDelay: 500,
                processing: true,
                serverSide: true,
                lengthChange: false,
                searching: false,
                pagingType: "simple_numbers",
                ajax: {
                    url: "/dashboard/user/headlines/suggested/list",
                    type: 'POST',

                    data: function(d) {
                        d.search = {
                            value: customSearchInput ?? $('#customSearchInput').val(), // O valor do input de pesquisa
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
                        data: 'Data'
                    },
                    {
                        data: 'Headline'
                    },
                    {
                        data: 'Mode'
                    },
                    {
                        data: 'Actions',
                        responsivePriority: -1
                    },
                ],
                columnDefs: [{
                        targets: 0,
                        render: (data, type, row) => {
                            return '<input type="checkbox" class="form-check-input suggested-checkbox" value="' +
                                row
                                .ID + '" data-suggested-id="' + row.ID + '">';
                        },
                        orderable: false,
                        searchable: false
                    },
                    {
                        // The `data` parameter refers to the data for the cell (defined by the
                        // `data` option, which defaults to the column being worked with, in
                        // this case `data: 0`.
                        targets: 1,
                        render: (data, type, row) => '<span>' + data + '</span>'
                    },
                    {
                        targets: 2,
                        render: (data, type, row) => {
                            return '<td data-label="Data"><div class="d-flex py-1 align-items-center"><div class="flex-fill"><div>' +
                                row.Data + '</div></div></div></td>'
                        }
                    },
                    {
                        targets: 3,
                        orderable: false,
                        render: (data, type, row) => {
                            var roadmapBadge = row.Roadmap ?
                                '<span class="badge bg-primary text-white me-2">Roteiro criado</span>' :
                                '';
                            return '<td data-label="Headline"><div class="d-flex py-1 align-items-center"><div class="flex-fill"><div class="font-weight-medium">' +
                                row.Headline +
                                '</div><div class="text-secondary mt-2"><span class="me-3"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-eye"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M10 12a2 2 0 1 0 4 0a2 2 0 0 0 -4 0" /><path d="M21 12c-2.4 4 -5.4 6 -9 6c-3.6 0 -6.6 -2 -9 -6c2.4 -4 5.4 -6 9 -6c3.6 0 6.6 2 9 6" /></svg> ' +
                                formatNumber(row.Result) +
                                '</span><span class="me-3"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-heart"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M19.5 12.572l-7.5 7.428l-7.5 -7.428a5 5 0 1 1 7.5 -6.566a5 5 0 1 1 7.5 6.572" /></svg> ' +
                                formatNumber(row.Likes) +
                                '</span><span class="me-3"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-message-circle"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M3 20l1.3 -3.9c-2.324 -3.437 -1.426 -7.872 2.1 -10.374c3.526 -2.501 8.59 -2.296 11.845 .48c3.255 2.777 3.695 7.266 1.029 10.501c-2.666 3.235 -7.615 4.215 -11.574 2.293l-4.7 1" /></svg> ' +
                                formatNumber(row.Comments) + '</span>' + roadmapBadge +
                                '</div></div></div></td>'
                        }
                    },
                    {
                        targets: 4,
                        render: (data, type, row) => {
                            const style = `display: block; padding: 3px 15px; border-radius: 25px; border: 1px solid #FFFFFF33; font-size: 1rem; color: #FFFFFF;`;

                            var mode = row.Mode == 'automatic' ?
                                `<span class="w-100 d-flex align-items-center justify-content-center status-badge azure"
                                    style="background-color: #3B5CFF; ${style}">Automático</span>` :
                                `<span class="w-100 d-flex align-items-center justify-content-center status-badge"
                                    style="background-color: #00C853; ${style};">Manual</span>`;

                            return '<td data-label="Mode"><div class="d-flex py-1 align-items-center"><div class="flex-fill"><div class="text-secondary">' +
                                mode + '</div></div></div></td>'
                        }
                    },

                    {
                        render: function(data, type, row) {
                            // return '<a href="javascript:void(0)" id="'+row.ID+'" class="btn btn_blue jwc_headlines_geradas_1"><span class="icon-eye icon-notext"></span></a>'
                            var buttons = '<div class="btn-list flex-nowrap">' +
                                '<a href="javascript:;" style="width: 40px !important; height: 40px !important; padding: 0 !important;" id="' +
                                row.ID +
                                '" class="rounded-circle btn btn-outline-blue w-100 btn-icon j_headlines_suggesteds_edit" ' +
                                'data-headline-id="' + row.ID + '" ' +
                                'data-structure-id="' + row.Structure + '" ' +
                                'data-headline="' + encodeURIComponent(row.Headline) + '" >' +
                                '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-edit"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M7 7h-1a2 2 0 0 0 -2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2 -2v-1" /><path d="M20.385 6.585a2.1 2.1 0 0 0 -2.97 -2.97l-8.415 8.385v3h3l8.385 -8.415z" /><path d="M16 5l3 3" /></svg>' +
                                '</a>';

                            
                            // Botão de link viral - só aparece se EngReversaResultId não for null
                            if (row.EngReversaResultId) {
                                buttons += '<a href="/dashboard/user/library?viral_id=' + row
                                    .EngReversaResultId +
                                    '" target="_blank" style="width: 40px !important; height: 40px !important; padding: 0 !important;" ' +
                                    'class="rounded-circle btn btn-outline-green w-100 btn-icon" title="Ver Viral na Biblioteca">' +
                                    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-video"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M15 10l4.553 -2.276a1 1 0 0 1 1.447 .894v6.764a1 1 0 0 1 -1.447 .894l-4.553 -2.276v-4z" /><path d="M3 6m0 2a2 2 0 0 1 2 -2h8a2 2 0 0 1 2 2v8a2 2 0 0 1 -2 2h-8a2 2 0 0 1 -2 -2z" /></svg>' +
                                    '</a>';
                            }

                            buttons +=
                                '<a href="javascript:;" style="width: 40px !important; height: 40px !important; padding: 0 !important;" data-headline="' +
                                encodeURIComponent(row.Headline) + '" id="' + row.ID +
                                '" class="rounded-circle btn btn-outline-purple w-100 btn-icon j_headlines_suggesteds_advanced_roadmap" data-headline-id="' +
                                (row.HeadlineId || row.ID) + '" title="Roteiro Avançado">' +
                                '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-wand"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M6 21l15 -15l-3 -3l-15 15l3 3" /><path d="M15 6l3 3" /><path d="M9 3a2 2 0 0 0 2 2a2 2 0 0 0 -2 2a2 2 0 0 0 -2 -2a2 2 0 0 0 2 -2" /><path d="M19 13a2 2 0 0 0 2 2a2 2 0 0 0 -2 2a2 2 0 0 0 -2 -2a2 2 0 0 0 2 -2" /></svg>' +
                                '</a>';
                            buttons +=
                                '<a href="javascript:;" style="width: 40px !important; height: 40px !important; padding: 0 !important;" id="' +
                                row.ID +
                                '" class="rounded-circle btn btn-outline-danger w-100 btn-icon j_headlines_suggesteds_delete" data-headline-id="' +
                                (row.HeadlineId || row.ID) + '" data-headline="' +
                                encodeURIComponent(row.Headline) +
                                '"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-trash"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M4 7l16 0" /><path d="M10 11l0 6" /><path d="M14 11l0 6" /><path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12" /><path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3" /></svg></a></div>';

                            return buttons;
                        },
                        orderable: false,
                        targets: 5
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
                        "next": `
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
            $('#select-all-suggested').on('change', function() {
                var isChecked = $(this).prop('checked');
                $('.suggested-checkbox').prop('checked', isChecked);
                toggleDeleteButtonSuggested();
            });

            // Gerenciar seleção individual de checkboxes
            $(document).on('change', '.suggested-checkbox', function() {
                var totalCheckboxes = $('.suggested-checkbox').length;
                var checkedCheckboxes = $('.suggested-checkbox:checked').length;

                $('#select-all-suggested').prop('checked', totalCheckboxes === checkedCheckboxes);
                toggleDeleteButtonSuggested();
            });

            // Função para mostrar/ocultar botão de exclusão em massa
            function toggleDeleteButtonSuggested() {
                var checkedCount = $('.suggested-checkbox:checked').length;
                if (checkedCount > 0) {
                    $('#btn-delete-multiple-suggested').show();
                    $('#btn-delete-multiple-suggested').html(
                        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon me-2"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M4 7l16 0"></path><path d="M10 11l0 6"></path><path d="M14 11l0 6"></path><path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12"></path><path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3"></path></svg>Excluir Selecionados (' +
                        checkedCount + ')');
                } else {
                    $('#btn-delete-multiple-suggested').hide();
                }
            }

            // Exclusão em massa
            $('#btn-delete-multiple-suggested').on('click', function() {
                var selectedIds = [];
                $('.suggested-checkbox:checked').each(function() {
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
                $('#modal-suggesteds-delete-multiple-message').text(message);

                // Armazenar IDs selecionados para uso no confirm
                $('#modal-suggesteds-delete-multiple').data('selected-ids', selectedIds);

                // Abrir modal de confirmação
                $('#modal-suggesteds-delete-multiple').modal('show');
            });

            // Confirmar exclusão em massa
            $('#j_suggesteds_delete_multiple_confirm').on('click', function() {
                var selectedIds = $('#modal-suggesteds-delete-multiple').data('selected-ids');

                if (!selectedIds || selectedIds.length === 0) {
                    toastr.warning('Nenhuma headline selecionada.');
                    $('#modal-suggesteds-delete-multiple').modal('hide');
                    return;
                }

                var $button = $('#btn-delete-multiple-suggested');
                $button.prop('disabled', true);
                $button.html('<span class="spinner-border spinner-border-sm me-2"></span>Excluindo...');

                // Fechar modal
                $('#modal-suggesteds-delete-multiple').modal('hide');

                $.ajax({
                    url: '/dashboard/user/headlines/suggested/delete-multiple',
                    type: 'POST',
                    data: {
                        ids: selectedIds,
                        _token: $('meta[name="csrf-token"]').attr('content')
                    },
                    success: function(response) {
                        if (response.success) {
                            toastr.success(response.message);
                            // Desmarcar todos os checkboxes
                            $('.suggested-checkbox').prop('checked', false);
                            $('#select-all-suggested').prop('checked', false);
                            toggleDeleteButtonSuggested();

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
                $('#select-all-suggested').prop('checked', false);
                toggleDeleteButtonSuggested();
            });
        });
    
/* ===== SCRIPT #26 @332793 attrs= len=520 */

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
    
/* ===== SCRIPT #27 @333336 attrs= len=10498 */

        $('body').on('click', '.j_headlines_suggesteds_edit', function() {
            // console.log('Botão de edição clicado!');

            // Limpar campos
            $('form#headline-suggested-edit').find('input[name="id"]').val('');
            $('form#headline-suggested-edit').find('input[name="headline"]').val('');
            $('form#headline-suggested-edit').find('textarea[name="roadmap"]').val('');

            // Esconder campo do roteiro e loading
            $('#roadmap-edit-container').hide();
            $('#roadmap-loading').hide();

            let id = $(this).attr('id');
            let headlineId = $(this).attr('data-headline-id');
            let headline = $(this).attr('data-headline');

            headline = decodeURIComponent(headline);

            // Verificar se o modal existe
            const modal = $('#modal-edit-headline-suggested');

            // Mostrar modal
            if (typeof modal.modal === 'function') {
                modal.modal('show');
            } else {
                console.error('Bootstrap modal não está disponível!');
                // Fallback: mostrar modal manualmente
                modal.show();
            }

            // Sempre ativar a aba "Roteiro" ao abrir o modal
            setTimeout(function() {
                // Remover active de todas as abas
                $('#modal-edit-headline-suggested .nav-link').removeClass('active');
                $('#modal-edit-headline-suggested .tab-pane').removeClass('active show');

                // Ativar a aba "Roteiro"
                var $roteiroTab = $('#edit-roadmap-tab-suggested');
                var $roteiroPane = $('#edit-roadmap-content-suggested');

                if ($roteiroTab.length && $roteiroPane.length) {
                    $roteiroTab.addClass('active');
                    $roteiroPane.addClass('active show');

                    // Usar Bootstrap Tab API para garantir ativação
                    var tab = new bootstrap.Tab($roteiroTab[0]);
                    tab.show();
                }
            }, 150);

            // Preencher campos básicos
            setTimeout(() => {
                $('form#headline-suggested-edit').find('input[name="id"]').val(id);
                $('form#headline-suggested-edit').find('input[name="headline"]').val(headline);
                $('form#headline-suggested-edit')
                    .data('chat-resource-id', headlineId)
                    .data('chat-resource-type', 'eng_reversa_headlines');

                // Buscar headline completa (com roteiro) via AJAX
                $('#roadmap-loading').show();

                $.ajax({
                    url: '/dashboard/user/headlines/suggested/get/' + headlineId,
                    type: 'GET',
                    success: function(data) {
                        $('#roadmap-loading').hide();
                        console.log('Dados recebidos do servidor:', data);

                        // Sempre mostrar o campo do roteiro no modal de edição
                        $('#roadmap-edit-container').show();

                        if (data.success && data.roadmap && data.roadmap.trim() !== '') {
                            // Tem roteiro - preencher o campo
                            console.log('Preenchendo roteiro no campo textarea');
                            $('form#headline-suggested-edit').find('textarea[name="roadmap"]')
                                .val(data.roadmap);
                        } else {
                            // Não tem roteiro - deixar campo vazio
                            console.log('Nenhum roteiro encontrado ou vazio');
                            $('form#headline-suggested-edit').find('textarea[name="roadmap"]')
                                .val('');
                        }

                        // Verificar se há search_text para mostrar a aba de fontes
                        if (data.search_text && data.search_text.trim() !== '') {
                            console.log(
                                'Dados de pesquisa encontrados no roteiro suggested');
                            // Mostrar a aba de fontes
                            $('#edit-sources-tab-li-suggested').show();

                            // Formatar e exibir o search_text
                            let searchTextFormatted = data.search_text.replace(/\n/g,
                                '<br>');
                            $('#edit-search-sources-content-suggested').html(
                                searchTextFormatted);
                        } else {
                            // Esconder a aba de fontes se não houver dados
                            $('#edit-sources-tab-li-suggested').hide();
                            $('#edit-search-sources-content-suggested').html('');
                        }
                    },
                    error: function(xhr) {
                        $('#roadmap-loading').hide();
                        // Sempre mostrar o campo do roteiro, mesmo em caso de erro
                        $('#roadmap-edit-container').show();
                        console.error('Erro ao buscar dados da headline:', xhr);
                        console.error('Response:', xhr.responseText);
                    }
                });
            }, 300);
        })

        $(document).ready(function() {
            // Sempre ativar a aba "Roteiro" ao abrir o modal
            $('#modal-edit-headline-suggested').on('shown.bs.modal', function() {
                setTimeout(function() {
                    // Remover active de todas as abas
                    $('#modal-edit-headline-suggested .nav-link').removeClass('active');
                    $('#modal-edit-headline-suggested .tab-pane').removeClass('active show');

                    // Ativar a aba "Roteiro"
                    var $roteiroTab = $('#edit-roadmap-tab-suggested');
                    var $roteiroPane = $('#edit-roadmap-content-suggested');

                    if ($roteiroTab.length && $roteiroPane.length) {
                        $roteiroTab.addClass('active');
                        $roteiroPane.addClass('active show');

                        // Usar Bootstrap Tab API para garantir ativação
                        var tab = new bootstrap.Tab($roteiroTab[0]);
                        tab.show();
                    }
                }, 50);
            });

            // Limpar dados ao fechar o modal de edição
            $('#modal-edit-headline-suggested').on('hidden.bs.modal', function() {
                $('#edit-sources-tab-li-suggested').hide();
                $('#edit-search-sources-content-suggested').html('');
            });

            // Evento de submit do formulário
            $('#headline-suggested-edit').on('submit', function(e) {
                e.preventDefault();
                // console.log('Formulário submetido!');

                var formData = new FormData(this);
                // console.log('FormData criado:', formData);

                $.ajax({
                    url: '/dashboard/user/headlines/suggested/update',
                    type: 'POST',
                    data: formData,
                    processData: false,
                    contentType: false,
                    success: function(data) {
                        // console.log('Sucesso:', data);
                        if (data.success) {
                            toastr.success(data.message);
                            $('#modal-edit-headline-suggested').modal('hide');
                            window.location.reload();
                        } else {
                            toastr.error(data.message || 'Erro ao atualizar headline');
                        }
                    },
                    error: function(xhr, status, error) {
                        console.error('Erro na requisição:', error);
                        console.error('Status:', status);
                        console.error('Response:', xhr.responseText);
                        toastr.error('Erro ao atualizar headline. Tente novamente.');
                    }
                });
            });

            // Evento de clique no botão de atualização
            $('#update_headline_suggested').on('click', function(e) {
                e.preventDefault();
                $('#headline-suggested-edit').submit();
            });

            $('#start_chat_suggested').on('click', function(e) {
                e.preventDefault();
                const resourceId = $('form#headline-suggested-edit').data('chat-resource-id');
                const resourceType = $('form#headline-suggested-edit').data('chat-resource-type');
                window.startChatMode(resourceId, resourceType, this);
            });
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
                            toastr.error(response.message || 'Não foi possível iniciar o modo chat.');
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
    
/* ===== SCRIPT #29 @343880 attrs= len=17895 */

        // Funções para o modal de roteiro
        function createRoadmap(headlineId) {
            console.log('Criar roteiro para headline:', headlineId);
            document.getElementById('roadmapContent').value = '';

            // Buscar a headline no DOM - usando o botão que foi clicado
            const clickedButton = document.querySelector(`[data-headline-id="${headlineId}"]`);
            const headlineText = clickedButton.getAttribute('data-headline');

            // Preencher o modal
            document.getElementById('roadmapHeadline').value = decodeURIComponent(headlineText);
            document.getElementById('roadmapHeadlineId').value = headlineId;

            // Mostrar estado inicial (formulário)
            showRoadmapState('form');

            // Abrir o modal
            const modal = new bootstrap.Modal(document.getElementById('createRoadmapModal'));
            modal.show();
        }

        function showRoadmapState(state) {
            // Esconder todos os estados
            document.getElementById('creatingRoadmapState').style.display = 'none';
            document.getElementById('createRoadmapFormState').style.display = 'none';
            document.getElementById('roadmapCreatedState').style.display = 'none';

            // Mostrar o estado solicitado
            switch (state) {
                case 'creating':
                    document.getElementById('creatingRoadmapState').style.display = 'block';
                    document.getElementById('createRoadmapBtn').style.display = 'none';
                    break;
                case 'form':
                    document.getElementById('createRoadmapFormState').style.display = 'block';
                    document.getElementById('createRoadmapBtn').style.display = 'inline-block';
                    break;
                case 'result':
                    document.getElementById('roadmapCreatedState').style.display = 'block';
                    document.getElementById('createRoadmapBtn').style.display = 'none';
                    break;
            }
        }

        function saveRoadmap() {
            const headlineId = document.getElementById('roadmapHeadlineId').value;
            const roadmapContent = document.getElementById('roadmapContent').value.trim();

            if (!roadmapContent) {
                toastr.error('Por favor, preencha as observações adicionais');
                return;
            }

            // Mostrar estado de criação
            showRoadmapState('creating');

            // AJAX para criar roteiro no backend usando endpoint correto
            $.ajax({
                url: "/dashboard/user/headlines/create-advanced-roadmap",
                type: 'POST',
                data: {
                    _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                    headline_id: headlineId,
                    context_data: roadmapContent,
                    mode: 'default',
                    ai_provider: 'claude'
                },
                success: function(data) {
                    if (data.success) {
                        // Iniciar long polling para verificar status
                        startLongPolling(headlineId);
                        toastr.success('Roteiro enviado para processamento!');
                    } else {
                        // Voltar para o formulário em caso de erro
                        showRoadmapState('form');
                        toastr.error(data.message || 'Erro ao criar o roteiro');
                    }
                },
                error: function(xhr) {
                    // Voltar para o formulário em caso de erro
                    showRoadmapState('form');
                    toastr.error('Erro ao criar o roteiro');
                    console.error(xhr);
                }
            });
        }

        function copyRoadmap() {
            const roadmapText = document.getElementById('roadmapResult').value;

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

        function viewRoadmap(headlineId) {
            // Buscar a headline no DOM - usando o botão que foi clicado
            const clickedButton = document.querySelector(`[data-headline-id="${headlineId}"]`);
            const headlineText = clickedButton.getAttribute('data-headline');

            // Preencher a headline no modal
            document.getElementById('viewRoadmapHeadline').value = decodeURIComponent(headlineText);

            // Buscar o roteiro via AJAX
            $.ajax({
                url: "/dashboard/user/roadmaps/reversa/show/" + headlineId,
                type: 'GET',
                data: {
                    headline_id: headlineId
                },
                success: function(data) {
                    if (data.success && data.roadmap_engreversa) {
                        // Preencher o roteiro no modal
                        document.getElementById('viewRoadmapContent').value = data.roadmap_engreversa;

                        // Abrir o modal
                        const modal = new bootstrap.Modal(document.getElementById('viewRoadmapModal'));
                        modal.show();
                    } else {
                        toastr.error(data.message || 'Roteiro não encontrado ou ainda não processado');
                    }
                },
                error: function(xhr) {
                    toastr.error('Erro ao buscar o roteiro');
                    console.error(xhr);
                }
            });
        }

        function copyViewRoadmap() {
            const roadmapText = document.getElementById('viewRoadmapContent').value;

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

        // Event delegation para os botões de ação
        document.addEventListener('click', function(e) {
            if (e.target.closest('.j_headlines_suggesteds_make_roadmap')) {
                e.preventDefault();
                const button = e.target.closest('.j_headlines_suggesteds_make_roadmap');
                const headlineId = button.getAttribute('data-headline-id');
                const headlineText = button.getAttribute('data-headline');

                if (headlineId && headlineId !== 'null' && headlineId !== 'undefined') {
                    // Verificar se já existe roteiro
                    checkExistingRoadmap(headlineId, headlineText);
                } else {
                    console.error('headlineId não encontrado no botão ou é null/undefined');
                }
            }

            if (e.target.closest('.j_headlines_suggesteds_delete')) {
                e.preventDefault();
                const button = e.target.closest('.j_headlines_suggesteds_delete');
                const headlineId = button.getAttribute('data-headline-id');
                const headlineText = button.getAttribute('data-headline');

                if (headlineId && headlineId !== 'null' && headlineId !== 'undefined') {
                    // Mostrar modal de confirmação
                    showDeleteConfirmation(headlineId, headlineText);
                } else {
                    console.error('headlineId não encontrado no botão de delete');
                }
            }
        });

        function checkExistingRoadmap(headlineId, headlineText) {
            // Buscar se já existe roteiro
            $.ajax({
                url: "/dashboard/user/roadmaps/reversa/show/" + headlineId,
                type: 'GET',
                data: {
                    headline_id: headlineId
                },
                success: function(data) {
                    if (data.success && data.roadmap_engreversa && data.status === 'completed') {
                        // Roteiro já existe e está completo - mostrar modal com o roteiro existente
                        showExistingRoadmap(headlineId, headlineText, data.roadmap_engreversa);
                    } else {
                        // Roteiro não existe ou não está completo - criar novo
                        createRoadmap(headlineId);
                    }
                },
                error: function(xhr) {
                    // Em caso de erro, tentar criar novo roteiro
                    createRoadmap(headlineId);
                }
            });
        }

        function showExistingRoadmap(headlineId, headlineText, roadmapContent) {
            // Preencher o modal com o roteiro existente
            document.getElementById('roadmapHeadlineResult').value = decodeURIComponent(headlineText);
            document.getElementById('roadmapResult').value = roadmapContent;
            document.getElementById('roadmapHeadlineId').value = headlineId;

            // Mostrar estado de resultado (roteiro existente)
            showRoadmapState('result');

            // Abrir o modal
            const modal = new bootstrap.Modal(document.getElementById('createRoadmapModal'));
            modal.show();
        }

        function recreateRoadmap() {
            const headlineId = document.getElementById('roadmapHeadlineId').value;
            const headlineText = document.getElementById('roadmapHeadlineResult').value;

            // Limpar o campo de observações
            document.getElementById('roadmapContent').value = '';

            // Preencher o modal para recriação
            document.getElementById('roadmapHeadline').value = headlineText;

            // Mostrar estado de formulário para recriar
            showRoadmapState('form');
        }

        function showDeleteConfirmation(headlineId, headlineText) {
            // Preencher o modal de confirmação
            document.getElementById('deleteHeadlineId').value = headlineId;
            document.getElementById('deleteHeadlineText').textContent = decodeURIComponent(headlineText);

            // Abrir o modal de confirmação
            const modal = new bootstrap.Modal(document.getElementById('deleteConfirmationModal'));
            modal.show();
        }

        function confirmDelete() {
            const headlineId = document.getElementById('deleteHeadlineId').value;

            if (!headlineId) {
                toastr.error('ID da headline não encontrado');
                return;
            }

            // AJAX para deletar
            $.ajax({
                url: '/dashboard/user/headlines/suggested/delete',
                type: 'POST',
                data: {
                    _token: 'HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC',
                    id: headlineId
                },
                success: function(data) {
                    if (data.success) {
                        toastr.success(data.message || 'Headline deletada com sucesso!');

                        // Fechar modal
                        const modal = bootstrap.Modal.getInstance(document.getElementById(
                            'deleteConfirmationModal'));
                        modal.hide();

                        // Recarregar a tabela
                        if (typeof table !== 'undefined') {
                            table.ajax.reload();
                        } else {
                            // Fallback: recarregar a página
                            window.location.reload();
                        }
                    } else {
                        toastr.error(data.message || 'Erro ao deletar headline');
                    }
                },
                error: function(xhr) {
                    toastr.error('Erro ao deletar headline');
                    console.error(xhr);
                }
            });
        }

        // Variáveis globais para long polling
        let pollingTimeout = null;
        let isPollingActive = false;

        function startLongPolling(headlineId) {
            let pollCount = 0;
            const maxPolls = 60; // Máximo 5 minutos (60 * 5 segundos)
            isPollingActive = true;

            function pollStatus() {
                if (!isPollingActive) {
                    return;
                }
                pollCount++;
                updateProgress(pollCount, maxPolls);

                $.ajax({
                    url: "/dashboard/user/roadmaps/reversa/show/" + headlineId,
                    type: 'GET',
                    data: {
                        headline_id: headlineId
                    },
                    success: function(data) {
                        if (data.success && data.roadmap_engreversa && data.status === 'completed') {
                            // Roteiro concluído com sucesso
                            document.getElementById('roadmapHeadlineResult').value = document.getElementById(
                                'roadmapHeadline').value;
                            document.getElementById('roadmapResult').value = data.roadmap_engreversa;
                            showRoadmapState('result');
                            toastr.success('Roteiro criado com sucesso!');
                            stopPolling();
                        } else if (data.success === false || data.status !== 'completed') {
                            // Roteiro ainda está sendo processado - continuar polling
                            if (pollCount >= maxPolls) {
                                showRoadmapState('form');
                                toastr.error(
                                    'Timeout: O roteiro está demorando mais que o esperado. Tente novamente.'
                                );
                                stopPolling();
                            } else {
                                pollingTimeout = setTimeout(pollStatus, 5000);
                            }
                        } else if (pollCount >= maxPolls) {
                            showRoadmapState('form');
                            toastr.error(
                                'Timeout: O roteiro está demorando mais que o esperado. Tente novamente.');
                            stopPolling();
                        } else {
                            pollingTimeout = setTimeout(pollStatus, 5000);
                        }
                    },
                    error: function(xhr) {
                        if (pollCount >= maxPolls) {
                            isPollingActive = false;
                            showRoadmapState('form');
                            toastr.error('Erro ao verificar status do roteiro');
                        } else {
                            pollingTimeout = setTimeout(pollStatus, 5000);
                        }
                    }
                });
            }
            pollingTimeout = setTimeout(pollStatus, 2000);
        }

        function updateProgress(current, max) {
            const percentage = Math.min((current / max) * 100, 100);
            document.querySelector('#creatingRoadmapState .progress-bar').style.width = percentage + '%';
            document.querySelector('#creatingRoadmapState .progress-bar').setAttribute('aria-valuenow', percentage);

            let statusText = '';
            if (current <= 6) {
                statusText = 'Iniciando processamento...';
            } else if (current <= 12) {
                statusText = 'Processando com GPT...';
            } else if (current <= 24) {
                statusText = 'Revisando com Assistant...';
            } else if (current <= 36) {
                statusText = 'Finalizando roteiro...';
            } else if (current <= 48) {
                statusText = 'Quase pronto...';
            } else {
                statusText = 'Aguarde, processamento em andamento...';
            }

            document.getElementById('progressStatus').textContent = statusText;
        }

        function stopPolling() {
            if (pollingTimeout) {
                clearTimeout(pollingTimeout);
                pollingTimeout = null;
            }
            isPollingActive = false;
        }

        function cancelRoadmapCreation() {
            stopPolling();
            showRoadmapState('form');
            toastr.info('Criação do roteiro cancelada');
        }

        // Parar polling quando modal for fechado
        document.addEventListener('hidden.bs.modal', function(e) {
            if (e.target.id === 'createRoadmapModal') {
                stopPolling();
            }
        });
    
/* ===== SCRIPT #30 @361803 attrs= len=801 */

        // Event listener para abrir modal de roteiro avançado (usando componente)
        document.addEventListener('click', function(e) {
            if (e.target.closest('.j_headlines_suggesteds_advanced_roadmap')) {
                e.preventDefault();
                const button = e.target.closest('.j_headlines_suggesteds_advanced_roadmap');
                const headlineId = button.getAttribute('data-headline-id');
                const headlineText = button.getAttribute('data-headline');

                if (headlineId && headlineId !== 'null' && headlineId !== 'undefined') {
                    AdvancedRoadmapModal.open(headlineId, headlineText);
                } else {
                    console.error('headlineId não encontrado');
                }
            }
        });
    
/* ===== SCRIPT #31 @362626 attrs= len=2677 */

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
    
/* ===== SCRIPT #33 @365396 attrs= len=605 */

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


/* ===== SCRIPT #34 @366020 attrs= len=9045 */

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


/* ===== SCRIPT #35 @375092 attrs= len=1554 */

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
        
/* ===== SCRIPT #36 @380608 attrs= len=1479 */

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
    
/* ===== SCRIPT #37 @382110 attrs=data-navigate-once="true" len=137 */
window.livewireScriptConfig = {"csrf":"HWvJLPiqDMlGcMojApMxvY6o0HwI3pvpTwhyUCdC","uri":"\/livewire\/update","progressBar":"","nonce":""};
/* ===== SCRIPT #41 @382531 attrs= len=4402 */

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
        
/* ===== SCRIPT #44 @387174 attrs=type="text/javascript" len=361 */

        window.$crisp = [];
        window.CRISP_WEBSITE_ID = "75cc752d-b49d-4b10-9a51-aeb70cf165c3";
                (function() {
            d = document;
            s = d.createElement("script");
            s.src = "https://client.crisp.chat/l.js";
            s.async = 1;
            d.getElementsByTagName("head")[0].appendChild(s);
        })();
    