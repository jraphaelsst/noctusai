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
    
