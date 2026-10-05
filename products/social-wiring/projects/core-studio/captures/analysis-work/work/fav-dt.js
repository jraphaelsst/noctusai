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
    
