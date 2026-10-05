$(document).on('click', '.j_headlines_view', function () {

    $('.j_headlines_headline_finale').html('')
    //$('.j_headlines_headline_old_1').html('')
    $('.j_headlines_payload').html('')
    // $('.j_headlines_params').html('')
    var id = $(this).attr('id');

    //add data-id to reprocess headlines
    $('.j_reprocess').attr('data-id', id)

    $.ajax({
        type: 'get',
        url: 'dashboard/user/headlines/view/'+id,
        //data: {callback: 'Estrutura', callback_action: 'headline_gpt', id: id},
        dataType: 'json',
        success: function (data) {
            //EXIBE CALLBACKS
            if (data.success) {
                // Formata o JSON para uma string bem formatada
                let formattedPayload = JSON.stringify(data.payload, null, 2); // '2' adiciona o espaçamento
                // let formattedParams = JSON.stringify(data.params, null, 2); // '2' adiciona o espaçamento

                // Substitui as quebras de linha por <br> e preserva o conteúdo
                formattedPayload = formattedPayload.replace(/\\r/g, '\r').replace(/\\n/g, '\n');

                $('#modal-view-headline').modal('show')
                //$('.j_headlines_headline_finale').html(data.headline_gpt)
                $('.j_headlines_headline_finale').html(data.headline_preview)
                //$('.j_headlines_headline_old_1').html(data.headline_old)
                console.log($('.j_headlines_payload'))
                $('.j_headlines_payload').html('<pre>' + Prism.highlight(formattedPayload, Prism.languages.json, 'json') + '</pre>'); // Exibe o JSON formatado
                //$('.j_headlines_params').html('<pre>' + Prism.highlight(formattedParams, Prism.languages.json, 'json') + '</pre>');

                // var formattedText = data.headline_gpt.replace(/<br\s*\/?>/gi, "\n");
                // $('.j_headline_edit').text(formattedText)

                // Ajustar altura dos textareas após carregar o conteúdo
                setTimeout(function() {
                    adjustAllTextareas();
                }, 100);

                const structure_count = data?.structure_count ?? null;
                const headlines_count = data?.headline_count ?? 0;
 
                if((structure_count || structure_count === 0) && structure_count < 5 && headlines_count < 10){
                    let mensage = `
                            Foram geradas poucas headlines porque há poucas estruturas compatíveis com as opções selecionadas.
                            Ajuste os filtros e gere novamente para obter mais variações.`;

                    if(structure_count <= 0 && headlines_count <= 0){
                        mensage = `
                            Nenhuma headline foi gerada porque não há estruturas compatíveis com as opções atuais.
                            Ajuste os filtros e gere novamente para ver resultados.`;
                    }
                    const element = $('#warning-minimum-quantity-structures');
                    if(element) element.removeClass('d-none').html(`
                        <div class="alert alert-warning d-flex align-items-center mb-3" role="alert">
                            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
                                viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                                stroke-linecap="round" stroke-linejoin="round"
                                class="icon icon-tabler icons-tabler-outline icon-tabler-info-circle me-2">
                                <path stroke="none" d="M0 0h24v24H0z" fill="none" />
                                <path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0" />
                                <path d="M12 9h.01" />
                                <path d="M11 12h1v4h1" />
                            </svg>
                            <div>
                                <strong>AVISO:</strong> ${mensage}
                            </div>
                        </div>    
                    `);
                }

                // Ajustar também quando o modal estiver completamente visível
                $('#modal-view-headline').on('shown.bs.modal', function() {
                    setTimeout(function() {
                        adjustAllTextareas();
                    }, 200);
                });
            }
        }
    });

    $('.jwc_contact_modal_headlines_geradas').fadeIn(200);
    return false;
});

$('#modal-view-headline').on('hidden.bs.modal', function () {
    const element = $('#warning-minimum-quantity-structures');
    if(element) element.addClass('d-none').html(``);
});

$('body').on('click', '.j_reprocess', function(){
    var headline_id = $(this).attr('data-id')
    $(this).closest('.dropdown-menu').removeClass('show');

    $.ajax({
        type: "get",
        url: "/dashboard/user/headlines/reprocess/"+headline_id,
        // data: formData,
        // dataType: 'JSON',
        contentType: false,
        processData: false,
        success: function(data){
            toastr[data.type](data.message);
            setTimeout(function(){
                //console.log(data)

                //location.href = '/dashboard/customers'
            }, 1000);

            if(data.refresh){
                setTimeout(function(){
                    window.location.reload();
                }, 1000);
            }
        },
        error: function(data){
            // Trata apenas erros não relacionados ao CSRF
            if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message.toLowerCase().includes('csrf'))) {
                if (data.responseJSON && (data.responseJSON.error || data.responseJSON.errors)) {
                    if(data.responseJSON.errors){
                        var errors = data.responseJSON.errors;
                        $.each(errors, function(index, value) {
                            toastr.error(value);
                        });
                    } else {
                        toastr.error(data.responseJSON.message);
                    }
                } else {
                    toastr.error('Ocorreu um erro ao reprocessar a Headline.');
                }
            }
        }
    });
    return false;
});

$('form#apply-headlines-box').submit(function (e) {
    "use strict";
    e.preventDefault();

    $('#apply_box_headlines_button').prop('disabled', true);
    $('#apply_box_headlines_button').text('Aguarde adicionando...');

    var formData = new FormData(this);

    $.ajax({
        type: "post",
        url: "/dashboard/box-headlines/add",
        data: formData,
        // dataType: 'JSON',
        contentType: false,
        processData: false,
        success: function(data){
            //toastr[data.type](data.message);

            if(data.success) {
                toastr[data.type](data.message);
                $('#modal-edit-headline').modal('hide');
                $('#offcanvasEnd').offcanvas('show');
                $('.j_box-headlines-list').html(data.box_headlines)
                $('.j_headline_icon_box').fadeIn();
            }

            $('#apply_box_headlines_button').prop('disabled', false);
            $('#apply_box_headlines_button').html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                '                            Adicionar na Box');

        },
        error: function(data) {
            // Trata apenas erros não relacionados ao CSRF
            if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message.toLowerCase().includes('csrf'))) {
                if (data.responseJSON && (data.responseJSON.error || data.responseJSON.errors)) {
                    if(data.responseJSON.errors){
                        var errors = data.responseJSON.errors;
                        $.each(errors, function(index, value) {
                            toastr.error(value);
                        });
                    } else {
                        toastr.error(data.responseJSON.message);
                    }
                } else {
                    toastr.error('Ocorreu um erro ao adicionar na Box.');
                }
            }

            $('#apply_box_headlines_button').prop('disabled', false);
            $('#apply_box_headlines_button').html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                '                            Adicionar na Box');
        }
    });

    return false;
});

//MAKE
// Placeholder do TomSelect de assuntos (variáveis) — mesmo texto do <option> vazio no blade
var HEADLINES_VARIABLES_PLACEHOLDER_DEFAULT = 'Selecione o assunto que deseja gerar';
var HEADLINES_VARIABLES_PLACEHOLDER_LOADING = 'Carregando assuntos…';
var HEADLINES_VARIABLES_PLACEHOLDER_ERROR = 'Não foi possível carregar. Tente alterar "Falar sobre" acima.';

function setVariablesTomSelectPlaceholder(ts, text) {
    if (!ts) {
        return;
    }
    ts.settings.placeholder = text;
    if (typeof ts.inputState === 'function') {
        ts.inputState();
    }
}

document.addEventListener("DOMContentLoaded", function () {
    var el = document.getElementById('make-headlines-select-variables-user');
    if (el) {
        new TomSelect(el, {
            copyClassesToDropdown: false,
            dropdownParent: 'body',
            controlInput: '<input>',
            placeholder: HEADLINES_VARIABLES_PLACEHOLDER_DEFAULT,
            onItemAdd: function () {
                // LIMPA o texto digitado após selecionar
                this.setTextboxValue('');
                this.refreshOptions(false);
            },
            render:{
                item: function(data, escape) {
                    if (data.customProperties) {
                        return '<div><span class="dropdown-item-indicator">' + data.customProperties + '</span>' + escape(data.text) + '</div>';
                    }
                    return '<div>' + escape(data.text) + '</div>';
                },
                option: function(data, escape){
                    // Verificar se a opção está desabilitada (vem do data.disabled ou do option original)
                    const optionElement = el.querySelector('option[value="' + data.value + '"]');
                    const isDisabled = (data.disabled === true) || (optionElement && optionElement.disabled);
                    const disabledClass = isDisabled ? ' disabled opacity-50' : '';
                    const disabledStyle = isDisabled ? ' style="cursor: not-allowed; opacity: 0.5; pointer-events: none;"' : '';
                    const disabledAttr = isDisabled ? ' data-disabled="true"' : '';

                    if (data.customProperties) {
                        return '<div class="option' + disabledClass + '"' + disabledStyle + disabledAttr + '><span class="dropdown-item-indicator">' + data.customProperties + '</span>' + escape(data.text) + '</div>';
                    }
                    return '<div class="option' + disabledClass + '"' + disabledStyle + disabledAttr + '>' + escape(data.text) + '</div>';
                },
            },
            onOptionAdd: function(value) {
                // Prevenir adicionar opções desabilitadas
                const optionElement = el.querySelector('option[value="' + value + '"]');
                if (optionElement && optionElement.disabled) {
                    this.removeItem(value, true); // Remove se tentar adicionar
                    return false; // Impede adicionar a opção
                }
            },
        });
    }

    // TomSelect para assuntos virais
    var viralTopicsEl = document.getElementById('make-headlines-viral-topics');
    if (viralTopicsEl) {
        new TomSelect(viralTopicsEl, {
            copyClassesToDropdown: false,
            dropdownParent: 'body',
            controlInput: '<input>',
            onItemAdd: function () {
                // LIMPA o texto digitado após selecionar
                this.setTextboxValue('');
                this.refreshOptions(false);
            },
            render:{
                item: function(data, escape) {
                    return '<div>' + escape(data.text) + '</div>';
                },
                option: function(data, escape){
                    return '<div>' + escape(data.text) + '</div>';
                },
            },
        });
    }

    // TomSelect para perfis de referência
    var profilesEl = document.getElementById('make-headlines-profiles');
    if (profilesEl) {
        new TomSelect(profilesEl, {
            copyClassesToDropdown: false,
            dropdownParent: 'body',
            controlInput: '<input>',
            maxItems: 2,
            create: true,
            createOnBlur: true,
            createFilter: function(input) {
                // Permite criar novos perfis se não estiver vazio
                return input.length > 0;
            },
            createItem: function(input, callback) {
                // Para novos perfis, usar prefixo para identificar
                callback({value: 'new:' + input, text: input});
            },
            onItemAdd: function () {
                // LIMPA o texto digitado após selecionar
                this.setTextboxValue('');
                this.refreshOptions(false);
            },
            render:{
                item: function(data, escape) {
                    return '<div>' + escape(data.text) + '</div>';
                },
                option: function(data, escape){
                    return '<div>' + escape(data.text) + '</div>';
                },
                'option_create': function(data, escape) {
                    return '<div class="create">Adicionar <strong>' + escape(data.input) + '</strong>&hellip;</div>';
                },
            },
        });
    }

    // Inicializar TomSelect para perfis na seção "Sobre mim e Meu público"
    var profilesMePublicEl = document.getElementById('make-headlines-profiles-me-public');
    if (profilesMePublicEl) {
        new TomSelect(profilesMePublicEl, {
            copyClassesToDropdown: false,
            dropdownParent: 'body',
            controlInput: '<input>',
            maxItems: 2,
            create: true,
            createOnBlur: true,
            createFilter: function(input) {
                // Permite criar novos perfis se não estiver vazio
                return input.length > 0;
            },
            createItem: function(input, callback) {
                // Para novos perfis, usar prefixo para identificar
                callback({value: 'new:' + input, text: input});
            },
            onItemAdd: function () {
                // LIMPA o texto digitado após selecionar
                this.setTextboxValue('');
                this.refreshOptions(false);
            },
            render:{
                item: function(data, escape) {
                    return '<div>' + escape(data.text) + '</div>';
                },
                option: function(data, escape){
                    return '<div>' + escape(data.text) + '</div>';
                },
                'option_create': function(data, escape) {
                    return '<div class="create">Adicionar <strong>' + escape(data.input) + '</strong>&hellip;</div>';
                },
            },
        });
    }

    // Inicializar TomSelect para formatos de vídeo na seção "Viral"
    var formatVideosEl = document.getElementById('make-headlines-format-videos');
    if (formatVideosEl) {
        new TomSelect(formatVideosEl, {
            copyClassesToDropdown: false,
            dropdownParent: 'body',
            controlInput: '<input>',
            create: false,
            onItemAdd: function () {
                // LIMPA o texto digitado após selecionar
                this.setTextboxValue('');
                this.refreshOptions(false);
            },
            render:{
                item: function(data, escape) {
                    return '<div>' + escape(data.text) + '</div>';
                },
                option: function(data, escape){
                    return '<div>' + escape(data.text) + '</div>';
                },
            },
        });
    }

    // Inicializar TomSelect para formatos de vídeo na seção "Sobre mim e Meu público"
    var formatVideosMePublicEl = document.getElementById('make-headlines-format-videos-me-public');
    if (formatVideosMePublicEl) {
        new TomSelect(formatVideosMePublicEl, {
            copyClassesToDropdown: false,
            dropdownParent: 'body',
            controlInput: '<input>',
            create: false,
            onItemAdd: function () {
                // LIMPA o texto digitado após selecionar
                this.setTextboxValue('');
                this.refreshOptions(false);
            },
            render:{
                item: function(data, escape) {
                    return '<div>' + escape(data.text) + '</div>';
                },
                option: function(data, escape){
                    return '<div>' + escape(data.text) + '</div>';
                },
            },
        });
    }

    // Inicializar estado dos elementos baseado no radio selecionado
    var selectedWho = $('input[name="who"]:checked').val();
    if(selectedWho === 'choose') {
        $('.divViralTopics').hide();
        $('.divCustomSubject').show();
    } else if (selectedWho === 'viral') {
        $('.divCustomSubject').hide();
        $('.divViralTopics').show();
    }

    // Carga inicial: o script do blade pode disparar `change` em `who` antes do TomSelect existir;
    // evitamos o setTimeout duplicado que gerava duas requests e fechava o dropdown no meio da seleção.
    var initialWhoForVariables = $('#modal-make-headlines input[name="who"]:checked').val();
    if (initialWhoForVariables) {
        fetchVariablesTypeForWho(initialWhoForVariables);
    }
});

var headlinesVariablesTypeXhr = null;
var headlinesVariablesTypeRequestGen = 0;

function fetchVariablesTypeForWho(who) {
    var tomSelect = document.querySelector('#make-headlines-select-variables-user');
    if (!who || !tomSelect || !tomSelect.tomselect) {
        return;
    }
    var ts = tomSelect.tomselect;
    var reqId = ++headlinesVariablesTypeRequestGen;

    if (headlinesVariablesTypeXhr) {
        headlinesVariablesTypeXhr.abort();
        headlinesVariablesTypeXhr = null;
    }

    if (typeof ts.close === 'function') {
        ts.close();
    }

    ts.clear();
    ts.clearOptions();
    setVariablesTomSelectPlaceholder(ts, HEADLINES_VARIABLES_PLACEHOLDER_LOADING);
    if (ts.wrapper) {
        ts.wrapper.style.opacity = '0.72';
        ts.wrapper.style.pointerEvents = 'none';
    }
    ts.refreshOptions(false);

    headlinesVariablesTypeXhr = $.ajax({
        type: 'get',
        url: '/dashboard/user/variables/type/' + who,
        dataType: 'json',
        complete: function () {
            headlinesVariablesTypeXhr = null;
        },
        success: function (data) {
            if (reqId !== headlinesVariablesTypeRequestGen) {
                return;
            }
            if (ts.wrapper) {
                ts.wrapper.style.opacity = '';
                ts.wrapper.style.pointerEvents = '';
            }
            ts.clear();
            ts.clearOptions();
            setVariablesTomSelectPlaceholder(ts, HEADLINES_VARIABLES_PLACEHOLDER_DEFAULT);
            if (data.content_option) {
                var parser = new DOMParser();
                var doc = parser.parseFromString(data.content_option, 'text/html');
                var options = Array.from(doc.querySelectorAll('option'))
                    .filter(function (option) {
                        return option.value;
                    })
                    .map(function (option) {
                        return {
                            value: option.value,
                            text: option.textContent,
                            disabled: option.disabled
                        };
                    });
                ts.addOptions(options);
                ts.refreshItems();
            }
            if (typeof ts.inputState === 'function') {
                ts.inputState();
            }
        },
        error: function (_xhr, status) {
            if (reqId !== headlinesVariablesTypeRequestGen) {
                return;
            }
            if (status === 'abort') {
                return;
            }
            if (ts.wrapper) {
                ts.wrapper.style.opacity = '';
                ts.wrapper.style.pointerEvents = '';
            }
            ts.clear();
            ts.clearOptions();
            setVariablesTomSelectPlaceholder(ts, HEADLINES_VARIABLES_PLACEHOLDER_ERROR);
            ts.addOption({
                value: '',
                text: 'Erro ao carregar a lista de assuntos.',
                disabled: true
            });
            if (typeof ts.inputState === 'function') {
                ts.inputState();
            }
        }
    });
}

$('#modal-make-headlines input[name="who"]').on('change', function(){
    let who = $(this).val();

    thinkForMe(who);

    // Controlar exibição do textarea para assunto personalizado com efeito fade (somente modo viral)
    if(who === 'choose') {
        $('.divViralTopics').fadeOut(300, function() {
            $('.divCustomSubject').fadeIn(300);
        });
    } else if (who === 'viral') {
        $('.divCustomSubject').fadeOut(300, function() {
            $('.divViralTopics').fadeIn(300);
        });
    }

    fetchVariablesTypeForWho(who);
});
function thinkForMe(who){
    if(who == 'ai'){
        $('#make-headlines-select-variables-user').val('all').trigger('change');
        $(".thinkForMe").css("display", "none");
    }else if(who == 'choose'){
        $(".thinkForMe").css("display", "block");
        $('.divViralTopics').fadeOut(300, function() {
            $('.divCustomSubject').fadeIn(300);
        });
    }else if(who == 'viral'){
        $(".thinkForMe").css("display", "block");
        $('.divCustomSubject').fadeOut(300, function() {
            $('.divViralTopics').fadeIn(300);
        });
    } else {
        // public, me, search, etc.: não alternar blocos exclusivos de Assuntos Virais
        $(".thinkForMe").css("display", "block");
    }
}

$('form#make-headlines-viral').submit(function (e) {
    "use strict";
    e.preventDefault();

    $('#make_headlines_button').prop('disabled', true);
    $('#make_headlines_button').html(`
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        Gerando Headlines...
    `);

    // Adicionar overlay de loading no modal
    $('#modal-make-headlines .modal-content').append(`
        <div class="modal-loading-overlay">
            <div class="modal-loading-content">
                <div class="spinner-border text-primary mb-3" role="status" style="width: 3rem; height: 3rem;">
                    <span class="visually-hidden">Carregando...</span>
                </div>
                <h5>Gerando suas Headlines...</h5>
                <p class="text-muted">Isso pode levar alguns segundos</p>
            </div>
        </div>
    `);

    var formData = new FormData(this);
    let who = $('input[name="who"]:checked').val();
    let whoChoose = $('input[name="who-choose"]:checked').val();

    formData.append('who', whoChoose || who);
    formData.delete('who-choose');

    // Sempre usar a mesma URL para ambos os tipos
    let submitUrl = "/dashboard/user/headlines/store-custom-subject";

    if(who == 'subject-moment'){
        formData.append('add_input', '2');
    }else{
        formData.append('add_input', '1');
    }

    console.log(formData)
    $.ajax({
        type: "post",
        url: submitUrl,
        data: formData,
        // dataType: 'JSON',
        contentType: false,
        processData: false,
        success: function(data){
            if(data.type && data.type != 'subject_action'){
                toastr[data.type](data.message);
            }

            if(data.type == 'subject_action' && data.subject.success == true){
                // Verifica se data.subject é uma string ou já é um objeto
                let subjectData = typeof data.subject === 'string' ? JSON.parse(data.subject) : data.subject;
                $('.j_content_make_headlines_select_subject_moment').html('');
                $('.j_content_make_headlines').fadeOut(300);
                $('#make-headlines-subject-moment').removeClass('d-none');
                $('#make_headlines_button_subject_moment_back').removeClass('d-none');
                $('form#make-headlines').fadeOut(300);
                $('form#make-headlines-subject-moment').fadeIn(300);
                $('.j_content_make_headlines_select_subject_moment').html(subjectData.subject).fadeIn(300);

                $('#make_headlines_button').prop('disabled', false);
                $('#make_headlines_button').html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                    '                            Gerar Headlines');
            }

            if(data.redirect){
                setTimeout(function(){
                    location.href = data.redirect;
                }, 1000);
            }
            if(data.refresh){
                setTimeout(function(){
                    window.location.reload();
                }, 1000);
            }

            // Novo tratamento para reload da página e abertura do modal
            if(data.reload_page){
                setTimeout(function(){
                    window.location.reload();
                }, 1000);
            }

            // Tratar abertura do modal após reload
            if(data.open_modal){
                // Armazenar dados do modal no localStorage para usar após reload
                localStorage.setItem('openModalAfterReload', JSON.stringify({
                    modal: data.open_modal,
                    data: data.modal_data || {}
                }));
            }

            // Tratar progresso de processamento assíncrono
            if(data.show_progress && data.id_headline){
                console.log('Iniciando progresso para headline ID:', data.id_headline);
                // Chamar função de progresso se estiver disponível
                if (typeof showProgressAnimation === 'function') {
                    showProgressAnimation(data.id_headline);
                } else {
                    console.log('Função showProgressAnimation não encontrada');
                    // Tentar chamar a função global
                    if (window.showProgressAnimation) {
                        window.showProgressAnimation(data.id_headline);
                    }
                }
            }
            if(data.button){
                $('#make_headlines_button').prop('disabled', false);
                $('#make_headlines_button').html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                    '                            Gerar Headlines');
            }
            if(data.reset){
                $('#make-headlines')[0].reset();
                $('#make-headlines-select-customers')[0].tomselect.clear();
                $('#make-headlines-select-structures')[0].tomselect.clear();
                $('#make-headlines-select-variables')[0].tomselect.clear();
                $('.j_all_values').fadeOut(300);
            }
            if(data.modalOut){
                $('#modal-make-headlines').modal('hide');
            }

            // Remover overlay de loading
            $('.modal-loading-overlay').fadeOut(300, function() {
                $(this).remove();
            });

        },
        error: function(data) {
            // Trata apenas erros não relacionados ao CSRF
            if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message.toLowerCase().includes('csrf'))) {
                if (data.responseJSON && (data.responseJSON.error || data.responseJSON.errors)) {
                    if(data.responseJSON.errors){
                        var errors = data.responseJSON.errors;
                        $.each(errors, function(index, value) {
                            toastr.error(value);
                        });
                    } else {
                        toastr.error(data.responseJSON.message);
                    }
                } else {
                    toastr.error('Ocorreu um erro ao gerar Headlines.');
                }
            }

            $('#make_headlines_button').prop('disabled', false);
            $('#make_headlines_button').html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                '                            Gerar Headlines');

            // Remover overlay de loading em caso de erro
            $('.modal-loading-overlay').fadeOut(300, function() {
                $(this).remove();
            });
        }
    });
    return false;
});

$('form#make-headlines-me').submit(function (e) {
    "use strict";
    e.preventDefault();

    const $form = $(this);
    const $button = $form.find('button[type="submit"]');

    $button.prop('disabled', true).text('Aguarde criando...');

    $('#make_headlines_button_subject_moment_make').prop('disabled', true);
    $('#make_headlines_button_subject_moment_make').text('Aguarde criando...');

    var formData = new FormData(this);

    var whoValue = $('input[name="who"]:checked').val();

    formData.append('who', whoValue);
    formData.append('add_input', '1');
    formData.append('input_user', $('form#make-headlines textarea[name="input_user"]').val());

    console.log(formData)
    $.ajax({
        type: "post",
        url: "/dashboard/user/headlines/store",
        data: formData,
        // dataType: 'JSON',
        contentType: false,
        processData: false,
        success: function(data){
            if(data.type && data.type != 'subject_action'){
                toastr[data.type](data.message);
            }

            if(data.type == 'subject_action' && data.subject.success == true){
                // Verifica se data.subject é uma string ou já é um objeto
                let subjectData = typeof data.subject === 'string' ? JSON.parse(data.subject) : data.subject;
                // $('.j_content_make_headlines').fadeOut(300);
                $('#make-headlines-subject-moment').removeClass('d-none');
                $('#make_headlines_button_subject_moment_back').removeClass('d-none');
                $('form#make-headlines').fadeOut(300);
                $('.j_content_make_headlines_select_subject_moment').html(subjectData.subject).fadeIn(300);

                $button.prop('disabled', false);
                // $button.html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                //     '                            Selecionar Assunto');
            }

            if(data.redirect){
                setTimeout(function(){
                    location.href = data.redirect;
                }, 1000);
            }
            if(data.refresh){
                setTimeout(function(){
                    window.location.reload();
                }, 1000);
            }
            if(data.button){
                $button.prop('disabled', false);
                $button.html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                    '                            Gerar Headlines');
            }
            if(data.reset){
                $('#make-headlines')[0].reset();
                $('#make-headlines-select-customers')[0].tomselect.clear();
                $('#make-headlines-select-structures')[0].tomselect.clear();
                $('#make-headlines-select-variables')[0].tomselect.clear();
                $('.j_all_values').fadeOut(300);
            }
            if(data.modalOut){
                $('#modal-make-headlines').modal('hide');
            }

            // Remover overlay de loading
            $('.modal-loading-overlay').fadeOut(300, function() {
                $(this).remove();
            });

        },
        error: function(data) {
            // Trata apenas erros não relacionados ao CSRF
            if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message.toLowerCase().includes('csrf'))) {
                if (data.responseJSON && (data.responseJSON.error || data.responseJSON.errors)) {
                    if(data.responseJSON.errors){
                        var errors = data.responseJSON.errors;
                        $.each(errors, function(index, value) {
                            toastr.error(value);
                        });
                    } else {
                        toastr.error(data.responseJSON.message);
                    }
                } else {
                    toastr.error('Ocorreu um erro ao gerar Headlines.');
                }
            }

            $button.prop('disabled', false);
            $button.html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                '                            Gerar Headlines');

            // Remover overlay de loading em caso de erro
            $('.modal-loading-overlay').fadeOut(300, function() {
                $(this).remove();
            });
        }
    });
    return false;
})



$('form#make-headlines-intelligent-search').submit(function (e) {
    "use strict";
    e.preventDefault();

    const $form = $(this);
    const $button = $form.find('button[type="submit"]');

    $button.prop('disabled', true).html(`
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        Buscando...
    `);

    // Adicionar overlay de loading no modal
    $('#modal-make-headlines .modal-content').append(`
        <div class="modal-loading-overlay">
            <div class="modal-loading-content">
                <div class="spinner-border text-primary mb-3" role="status" style="width: 3rem; height: 3rem;">
                    <span class="visually-hidden">Carregando...</span>
                </div>
                <h5>Buscando suas Headlines...</h5>
                <p class="text-muted">Isso pode levar alguns segundos</p>
            </div>
        </div>
    `);

    $('#make_headlines_button_subject_moment_make').prop('disabled', true);
    $('#make_headlines_button_subject_moment_make').text('Aguarde criando...');

    var formData = new FormData(this);

    var whoValue = $('input[name="who"]:checked').val();

    formData.append('who', whoValue);
    formData.append('add_input', '1');
    formData.append('input_user', $('form#make-headlines textarea[name="input_user"]').val());

    console.log(formData)
    $.ajax({
        type: "post",
        url: "/dashboard/user/headlines/store",
        data: formData,
        // dataType: 'JSON',
        contentType: false,
        processData: false,
        success: function(data){
            if(data.type && data.type != 'subject_action'){
                toastr[data.type](data.message);
            }

            if(data.type == 'subject_action' && data.subject.success == true){
                // Verifica se data.subject é uma string ou já é um objeto
                let subjectData = typeof data.subject === 'string' ? JSON.parse(data.subject) : data.subject;
                // $('.j_content_make_headlines').fadeOut(300);
                $('#make-headlines-subject-moment').removeClass('d-none');
                $('#make_headlines_button_subject_moment_back').removeClass('d-none');
                $('form#make-headlines').fadeOut(300);
                $('.j_content_make_headlines_select_subject_moment').html(subjectData.subject).fadeIn(300);

                $button.prop('disabled', false);
                // $button.html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                //     '                            Selecionar Assunto');
            }

            if(data.redirect){
                setTimeout(function(){
                    location.href = data.redirect;
                }, 1000);
            }
            if(data.refresh){
                setTimeout(function(){
                    window.location.reload();
                }, 1000);
            }
            if(data.button){
                $button.prop('disabled', false);
                $button.html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                    '                            Buscar Headlines');
            }
            if(data.reset){
                $('#make-headlines')[0].reset();
                $('#make-headlines-select-customers')[0].tomselect.clear();
                $('#make-headlines-select-structures')[0].tomselect.clear();
                $('#make-headlines-select-variables')[0].tomselect.clear();
                $('.j_all_values').fadeOut(300);
            }
            if(data.modalOut){
                $('#modal-make-headlines').modal('hide');
            }

            // Remover overlay de loading
            $('.modal-loading-overlay').fadeOut(300, function() {
                $(this).remove();
            });

        },
        error: function(data) {
            // Trata apenas erros não relacionados ao CSRF
            if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message.toLowerCase().includes('csrf'))) {
                if (data.responseJSON && (data.responseJSON.error || data.responseJSON.errors)) {
                    if(data.responseJSON.errors){
                        var errors = data.responseJSON.errors;
                        $.each(errors, function(index, value) {
                            toastr.error(value);
                        });
                    } else {
                        toastr.error(data.responseJSON.message);
                    }
                } else {
                    toastr.error('Ocorreu um erro ao buscar Headlines.');
                }
            }

            $button.prop('disabled', false);
            $button.html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                '                            Buscar Headlines');

            // Remover overlay de loading em caso de erro
            $('.modal-loading-overlay').fadeOut(300, function() {
                $(this).remove();
            });
        }
    });
    return false;
})


function clearTomSelects () {
    // Limpar TomSelects individuais
    if(document.querySelector('#make-headlines-viral-topics')?.tomselect) {
        document.querySelector('#make-headlines-viral-topics').tomselect.clear();
    }
    if(document.querySelector('#make-headlines-profiles')?.tomselect) {
        document.querySelector('#make-headlines-profiles').tomselect.clear();
    }
    if(document.querySelector('#make-headlines-format-videos')?.tomselect) {
        document.querySelector('#make-headlines-format-videos').tomselect.clear();
    }
    if(document.querySelector('#make-headlines-profiles-me-public')?.tomselect) {
        document.querySelector('#make-headlines-profiles-me-public').tomselect.clear();
    }
    if(document.querySelector('#make-headlines-format-videos-me-public')?.tomselect) {
        document.querySelector('#make-headlines-format-videos-me-public').tomselect.clear();
    }

    // Limpar TomSelects das opções avançadas
    if(!window.tomSelects) return;
    for (var key in window.tomSelects) {
        if (window.tomSelects.hasOwnProperty(key)) {
            window.tomSelects[key].clear();
        }
    }
}

$('body').on('change', 'input[name="who"]:checked', function(){
    let who = $(this).val();

    if(who == 'subject-moment'){
        $('.j_advanced_options').fadeOut(300);
        // $('.j_content_make_headlines').fadeOut(300);
        // $('#make-headlines-subject-moment').removeClass('d-none');
        // $('#make_headlines_button_subject_moment_back').removeClass('d-none');
        // $('form#make-headlines').fadeOut(300);
        // $('form#make-headlines-subject-moment').fadeIn(300);
    } else {
        $('.j_advanced_options').fadeIn(300);
    }
})

$('#make_headlines_button_subject_moment_back').on('click', function(){
    $('#make_headlines_button_subject_moment_back').addClass('d-none');
    $('form#make-headlines-subject-moment').fadeOut(300);
    $('form#make-headlines').fadeIn(300);
    $('#make_headlines_button_subject_moment_make').fadeOut(300);
    $('#make_headlines_button_subject_moment_next').fadeIn(300);

    $('.j_content_make_headlines_select_subject_moment_tom').fadeOut(300);

})

$('#make_headlines_button_subject_moment_next').on('click', function(){

    //verificar se o radio esta checked
    if(!$('input[name="subject_selected"]:checked').val()){
        toastr.error('Selecione um assunto para continuar.');
        return false;
    }

    $('.j_content_make_headlines_select_subject_moment').fadeOut(300);
    $('.j_content_make_headlines_select_subject_moment_tom').fadeIn(300);
    $('#make_headlines_button_subject_moment_next').fadeOut(300);
    $('#make_headlines_button_subject_moment_make').fadeIn(300);
    // $('#make_headlines_button_subject_moment_next').addClass('d-none');
    // $('#make_headlines_button_subject_moment_back').removeClass('d-none');
    // $('form#make-headlines-subject-moment').fadeIn(300);
})

$('.j_make_headlines_clear_fields').on('click', function() {
    clearTomSelects()
})

function handleCategoryClick(buttonSelector, containerSelector) {
    const classSelected = "btn-outline-dark active";
    const classUnselected = "btn-dark text-secondary";

    $(buttonSelector).on("click", function () {
        $(this).toggleClass(`${classSelected} ${classUnselected}`);
        const containerAdvancedOptions = $(containerSelector);
        const isVisible = containerAdvancedOptions.is(":visible");

        // Animação de exibição/ocultação
        if (isVisible) {
            containerAdvancedOptions.addClass("fade-out");
            setTimeout(() => {
                containerAdvancedOptions.fadeOut(300, () => {
                    clearTomSelects();
                    containerAdvancedOptions.removeClass("fade-out");
                });
            }, 50);
        } else {
            containerAdvancedOptions.fadeIn(300, () => {
                setTimeout(() => initializeAdvancedTomSelects(), 100);
            });
        }

        // Configuração do slider
        const slider = $("#customRange");
        const sliderColor1 = "#0054A6";
        const sliderColor2Default = "#25384f";
        let sliderColor2 = sliderColor2Default;

        function updateSliderBackground(value) {
            if (document.body.getAttribute("data-bs-theme") !== "dark") {
                sliderColor2 = "#dadfe5";
            }
            const min = parseFloat(slider.attr("min"));
            const max = parseFloat(slider.attr("max"));
            const percentage = ((value - min) / (max - min)) * 100;
            slider[0].style.background = `linear-gradient(to right, ${sliderColor1} ${percentage}%, ${sliderColor2} ${percentage}%)`;

           slider[0].value = value;
            slider[0].dispatchEvent(new Event('change', { bubbles: true }));
        }

        updateSliderBackground(slider.val());
        slider.off("input").on("input", function () {
            updateSliderBackground($(this).val());
        });
    });
}

handleCategoryClick("#set_headlines_categories", "#j_make_headlines_advanced_options");
handleCategoryClick("#set_headlines_categories-2", "#j_make_headlines_advanced_options_me_public");

$('body').on('click', '.j_headline_like', function(){
    let $this = $(this); // Armazena a referência ao elemento clicado
    let structure_id = $this.attr('data-structure-id');
    let headline = $this.attr('data-headline');
    let headline_id = $this.attr('data-headline-id');

    $.ajax({
        type: 'post',
        url: '/dashboard/user/headlines/like',
        data: {
            structure_id: structure_id,
            headline: headline,
            headline_id: headline_id
        },
        dataType: 'json',
        success: function(data){
            toastr[data.type](data.message);

            if(data.success){
                $this.html('<svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="currentColor"  class="icon icon-tabler icons-tabler-filled icon-tabler-heart"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M6.979 3.074a6 6 0 0 1 4.988 1.425l.037 .033l.034 -.03a6 6 0 0 1 4.733 -1.44l.246 .036a6 6 0 0 1 3.364 10.008l-.18 .185l-.048 .041l-7.45 7.379a1 1 0 0 1 -1.313 .082l-.094 -.082l-7.493 -7.422a6 6 0 0 1 3.176 -10.215z" /></svg>');
                $this.removeClass('j_headline_like');
                $this.addClass('j_headline_unlike');
            }
        },
        error: function(data) {
            // Trata apenas erros não relacionados ao CSRF
            if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message.toLowerCase().includes('csrf'))) {
                if (data.responseJSON && (data.responseJSON.error || data.responseJSON.errors)) {
                    if(data.responseJSON.errors){
                        var errors = data.responseJSON.errors;
                        $.each(errors, function(index, value) {
                            toastr.error(value);
                        });
                    } else {
                        toastr.error(data.responseJSON.message);
                    }
                } else {
                    toastr.error('Ocorreu um erro ao favoritar a Headline.');
                }
            }
        }
    });
    return false;
})

$('body').on('click', '.j_headline_unlike', function(){
    let $this = $(this); // Armazena a referência ao elemento clicado
    let structure_id = $this.attr('data-structure-id');
    let headline = $this.attr('data-headline');
    let headline_id = $this.attr('data-headline-id');

    $.ajax({
        type: 'post',
        url: '/dashboard/user/headlines/unlike',
        data: {
            structure_id: structure_id,
            headline: headline,
            headline_id: headline_id
        },
        dataType: 'json',
        success: function(data){
            toastr[data.type](data.message);

            if(data.success){
                $this.html('<svg  xmlns="http://www.w3.org/2000/svg"  width="24"  height="24"  viewBox="0 0 24 24"  fill="none"  stroke="currentColor"  stroke-width="2"  stroke-linecap="round"  stroke-linejoin="round"  class="icon icon-tabler icons-tabler-outline icon-tabler-heart-plus"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 20l-7.5 -7.428a5 5 0 1 1 7.5 -6.566a5 5 0 1 1 7.96 6.053" /><path d="M16 19h6" /><path d="M19 16v6" /></svg>');
                $this.removeClass('j_headline_unlike');
                $this.addClass('j_headline_like');
            }
        },
        error: function(data) {
            // Trata apenas erros não relacionados ao CSRF
            if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message.toLowerCase().includes('csrf'))) {
                if (data.responseJSON && (data.responseJSON.error || data.responseJSON.errors)) {
                    if(data.responseJSON.errors){
                        var errors = data.responseJSON.errors;
                        $.each(errors, function(index, value) {
                            toastr.error(value);
                        });
                    } else {
                        toastr.error(data.responseJSON.message);
                    }
                } else {
                    toastr.error('Ocorreu um erro desfavoritar a Headline.');
                }
            }
        }
    });
    return false;
})

$('body').on('click', '.j_headlines_favorites_edit', function(){
    // Limpar campos
    $('form#headline-favorite-edit').find('input[name="id"]').val('');
    $('form#headline-favorite-edit').find('input[name="headline"]').val('');
    $('form#headline-favorite-edit').find('textarea[name="roadmap"]').val('');

    // Esconder campo do roteiro e loading
    $('#roadmap-edit-container-favorite').hide();
    $('#roadmap-loading-favorite').hide();

    let id = $(this).attr('id');
    let headlineId = $(this).attr('data-headline-id');
    let headline = $(this).attr('data-headline');

    headline = decodeURIComponent(headline);

    // Verificar se o modal existe
    const modal = $('#modal-edit-headline-favorite');

    // Mostrar modal
    if (typeof modal.modal === 'function') {
        modal.modal('show');
    } else {
        console.error('Bootstrap modal não está disponível!');
        modal.show();
    }

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
    }, 150);

    // Preencher campos básicos
    setTimeout(() => {
        $('form#headline-favorite-edit').find('input[name="id"]').val(id);
        $('form#headline-favorite-edit').find('input[name="headline"]').val(headline);

        // Buscar headline completa (com roteiro) via AJAX
        $('#roadmap-loading-favorite').show();

        $.ajax({
            url: '/dashboard/user/headlines/favorites/get/' + id,
            type: 'GET',
            success: function(data) {
                $('#roadmap-loading-favorite').hide();

                if(data.success && data.roadmap && data.roadmap.trim() !== '') {
                    // Tem roteiro - mostrar campo e preencher
                    $('form#headline-favorite-edit').find('textarea[name="roadmap"]').val(data.roadmap);
                    $('#roadmap-edit-container-favorite').show();
                }
                // Se não tem roteiro, não mostrar o campo
            },
            error: function(xhr) {
                $('#roadmap-loading-favorite').hide();
                // Se der erro, não mostrar o campo do roteiro
                console.log('Erro ao buscar dados da headline:', xhr);
            }
        });
    }, 300);
})


function generateHeadlines(){
    console.log('generateHeadlines');
    // Preencher campos básicos
    $.ajax({
        url: '/dashboard/user/headlines/generate-sugeridas-day',
        type: 'POST',
        dataType: 'json',
        success: function(data) {
            console.log(data);
        },
        error: function(xhr) {
            console.log(xhr);
        }
    });
};
generateHeadlines();
$('form#headline-favorite-edit').submit(function (e) {
    "use strict";
    e.preventDefault();

    $('#update_headline_favorite').prop('disabled', true);
    $('#update_headline_favorite').text('Aguarde atualizando...');

    var formData = new FormData(this);

    $.ajax({
        type: "post",
        url: "/dashboard/user/headlines/favorites/update",
        data: formData,
        // dataType: 'JSON',
        contentType: false,
        processData: false,
        success: function(data){
            toastr[data.type](data.message);

            if(data.redirect){
                setTimeout(function(){
                    location.href = data.redirect;
                }, 1000);
            }
            if(data.refresh){
                setTimeout(function(){
                    window.location.reload();
                }, 1000);
            }
            if(data.button){
                $('#update_headline_favorite').prop('disabled', false);
                $('#update_headline_favorite').html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                    '                            Gerar Headlines');
            }
            if(data.reset){
                $('#make-headlines')[0].reset();
                $('#make-headlines-select-customers')[0].tomselect.clear();
                $('#make-headlines-select-structures')[0].tomselect.clear();
                $('#make-headlines-select-variables')[0].tomselect.clear();
                $('.j_all_values').fadeOut(300);
            }
            if(data.modalOut){
                $('#modal-make-headlines').modal('hide');
            }

            // Remover overlay de loading
            $('.modal-loading-overlay').fadeOut(300, function() {
                $(this).remove();
            });

        },
        error: function(data) {
            // Trata apenas erros não relacionados ao CSRF
            if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message || !data.responseJSON.message.toLowerCase().includes('csrf'))) {
                if (data.responseJSON && (data.responseJSON.error || data.responseJSON.errors)) {
                    if(data.responseJSON.errors){
                        var errors = data.responseJSON.errors;
                        $.each(errors, function(index, value) {
                            toastr.error(value);
                        });
                    } else {
                        toastr.error(data.responseJSON.message);
                    }
                } else {
                    toastr.error('Ocorreu um erro ao atualizar a Headline.');
                }
            }

            $('#update_headline_favorite').prop('disabled', false);
            $('#update_headline_favorite').html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                '                            Gerar Headlines');
        }
    });
    return false;
});

$('body').on('click', '.j_headlines_delete', function(){
    $('#modal-headlines-delete').modal('show');
    let id = $(this).attr('data-headline-id');
    $('.j_headlines_delete_confirm').attr('href', '/dashboard/user/headlines/delete/'+id);
})

$('body').on('click', '.j_headlines_favorites_delete', function(){
    $('#modal-favorites-delete').modal('show');
    let id = $(this).attr('id');
    $('.j_favorites_delete_confirm').attr('href', '/dashboard/user/headlines/favorites/delete/'+id);
})

//modal-favorites-make-roadmap
$('body').on('click', '.j_headlines_favorites_make_roadmap', function(){
    let headline = $(this).attr('data-headline');
    let structure_id = $(this).attr('data-structure-id');
    let headline_id = $(this).attr('id'); // Usar o ID do elemento (primary key do registro)

    $('form#favorites_make_roadmap').find('input[name="headline"]').val(headline);
    $('form#favorites_make_roadmap').find('input[name="structure_id"]').val(structure_id);
    $('form#favorites_make_roadmap').find('input[name="headline_id"]').val(headline_id);
    $('#modal-favorites-make-roadmap').modal('show');
})

$('form#favorites_make_roadmap').submit(function (e) {
    "use strict";
    e.preventDefault();

    $('#button_make_roadmap').prop('disabled', true);
    $('#button_make_roadmap').text('Aguarde criando...');

    var formData = new FormData(this);

    var head = formData.get('headline');

    // Remove o valor antigo e adiciona o novo codificado
    formData.delete('headline');
    formData.append('headline', decodeURIComponent(head));

    $.ajax({
        type: "post",
        url: "/dashboard/user/roadmaps/store",
        data: formData,
        contentType: false,
        processData: false,
        success: function(data){
            toastr[data.type](data.message);
            // return false;
            if(data.redirect){
                setTimeout(function(){
                    location.href = data.redirect;
                }, 1000);
            }
            if(data.refresh){
                setTimeout(function(){
                    window.location.reload();
                }, 1000);
            }
            if(data.button){
                $('#button_make_roadmap').prop('disabled', false);
                $('#button_make_roadmap').html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                    '                            Criar Roteiro');
            }
            if(data.success){
                $('#modal-show-roadmaps').modal('show');

                startProgressCheckRoadmaps(data.roadmap_ids);
            }
            if(data.reset){
                $('#make-headlines')[0].reset();
                $('#make-headlines-select-customers')[0].tomselect.clear();
                $('#make-headlines-select-structures')[0].tomselect.clear();
                $('#make-headlines-select-variables')[0].tomselect.clear();
                $('.j_all_values').fadeOut(300);
            }
            if(data.modalOut){
                $('#modal-make-headlines').modal('hide');
            }

            // Remover overlay de loading
            $('.modal-loading-overlay').fadeOut(300, function() {
                $(this).remove();
            });

        },
        error: function(data) {
            // Trata apenas erros não relacionados ao CSRF
            if (data.status !== 419 && (!data.responseJSON || !data.responseJSON.message || !data.responseJSON.message.toLowerCase().includes('csrf'))){
                if (data.responseJSON && (data.responseJSON.error || data.responseJSON.errors)) {
                    if(data.responseJSON.errors){
                        var errors = data.responseJSON.errors;
                        $.each(errors, function(index, value) {
                            toastr.error(value);
                        });
                    } else {
                        toastr.error(data.responseJSON.message);
                    }
                } else {
                    toastr.error('Ocorreu um erro ao criar o roteiro.');
                }
            }

            $('#button_make_roadmap').prop('disabled', false);
            $('#button_make_roadmap').html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                '                            Criar Roteiro');
        }
    });
    return false;
});

function startProgressCheckRoadmaps(roadmap_ids){

    const contRoadmaps = roadmap_ids.length;

    const interval = setInterval(function(){

        $.ajax({
            type: "post",
            url: "/dashboard/user/roadmaps/check-progress",
            data: {
                roadmap_ids: roadmap_ids
            },
            success: function(data){
                if(data.roadmapsSuccess.length == contRoadmaps){
                    clearInterval(interval);

                    if(data.roadmapsSuccess.length > 1){
                        $('.j_change_modal_size').removeClass('modal-lg');
                        $('.j_change_modal_size').addClass('modal-xl');
                        let templateHtml = '';
                        let cont = 1;
                        templateHtml += '<div class="row">';
                        data.roadmapsSuccess.forEach(function(roadmap){
                            templateHtml += `

                                    <div class="col-6">
                                        <h2 class="mb-3">Opção ${cont}</h2>
                                        <div class="accordion accordion-tabs">
                                            <div class="accordion-item">
                                                <div class="accordion-collapse collapse show pt-4">
                                                    <div class="accordion-body pt-0">
                                                        <div>
                                                        <p>
                                                            ${roadmap.roadmap_content.replace(/\n/g, '<br>')}
                                                        </p>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                        <a href="dashboard/user/roadmaps?open_id=${roadmap.id}" id="go_to_roadmap" href="javascript:;" class="btn btn-primary ms-auto"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>
                                            Ir para o Roteiro</a>
                                    </div>

                            `;
                            cont++;
                        });
                        templateHtml += '</div>';
                        $('.preload_roadmaps').html(templateHtml);
                    }else{
                        $('.j_change_modal_size').removeClass('modal-xl');
                        $('.j_change_modal_size').addClass('modal-lg');
                        let templateHtml = '';
                        let cont = 1;
                        templateHtml += '<div class="row">';
                        data.roadmapsSuccess.forEach(function(roadmap){
                            templateHtml += `

                                    <div class="col-12">
                                        <div class="accordion accordion-tabs">
                                            <div class="accordion-item">
                                                <div class="accordion-collapse collapse show pt-4">
                                                    <div class="accordion-body pt-0">
                                                        <div>
                                                        <p>
                                                            ${roadmap.roadmap_content.replace(/\n/g, '<br>')}
                                                        </p>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                        <a href="dashboard/user/roadmaps?open_id=${roadmap.id}" id="go_to_roadmap" href="javascript:;" class="btn btn-primary ms-auto"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>
                                            Ir para o Roteiro</a>
                                    </div>

                            `;
                            cont++;
                        });
                        templateHtml += '</div>';
                        $('.preload_roadmaps').html(templateHtml);
                    }

                }
            }
        });
    }, 5000);
}

document.addEventListener("DOMContentLoaded", function () {
    var el = document.getElementById('favorites-select-core-brains');
    if (el) {
        new TomSelect(el, {
            copyClassesToDropdown: false,
            dropdownParent: 'body',
            controlInput: '<input>',
            onItemAdd: function () {
                // LIMPA o texto digitado após selecionar
                this.setTextboxValue('');
                this.refreshOptions(false);
            },
            render:{
                item: function(data, escape) {
                    if (data.customProperties) {
                        return '<div><span class="dropdown-item-indicator">' + data.customProperties + '</span>' + escape(data.text) + '</div>';
                    }
                    return '<div>' + escape(data.text) + '</div>';
                },
                option: function(data, escape){
                    if (data.customProperties) {
                        return '<div><span class="dropdown-item-indicator">' + data.customProperties + '</span>' + escape(data.text) + '</div>';
                    }
                    return '<div>' + escape(data.text) + '</div>';
                },
            },
        });
    }
});

document.addEventListener("DOMContentLoaded", function () {
    var el = document.getElementById('favorites-select-core-beliefs');
    console.log('Elemento favorites-select-core-beliefs encontrado:', el);
    if (el) {
        console.log('Inicializando TomSelect para favorites-select-core-beliefs');

        // Verifica se TomSelect está disponível
        if (typeof TomSelect !== 'undefined') {
            new TomSelect(el, {
                copyClassesToDropdown: false,
                dropdownParent: 'body',
                controlInput: '<input>',
                onItemAdd: function () {
                // LIMPA o texto digitado após selecionar
                    this.setTextboxValue('');
                    this.refreshOptions(false);
                },
                render:{
                    item: function(data, escape) {
                        if (data.customProperties) {
                            return '<div><span class="dropdown-item-indicator">' + data.customProperties + '</span>' + escape(data.text) + '</div>';
                        }
                        return '<div>' + escape(data.text) + '</div>';
                    },
                    option: function(data, escape){
                        if (data.customProperties) {
                            return '<div><span class="dropdown-item-indicator">' + data.customProperties + '</span>' + escape(data.text) + '</div>';
                        }
                        return '<div>' + escape(data.text) + '</div>';
                    },
                },
            });
            console.log('TomSelect inicializado com sucesso para favorites-select-core-beliefs');
        }
    }
});

// document.addEventListener("DOMContentLoaded", function () {
//     var el = document.getElementById('make-headlines-select-assuntos-user');

//     if (el && window.TomSelect) {
//         var tomSelectInstance = new TomSelect(el, {
//             copyClassesToDropdown: false,
//             dropdownParent: 'body',
//             controlInput: '<input>',
//             render:{
//                 item: function(data, escape) {
//                     if (data.customProperties) {
//                         return '<div><span class="dropdown-item-indicator">' + data.customProperties + '</span>' + escape(data.text) + '</div>';
//                     }
//                     return '<div>' + escape(data.text) + '</div>';
//                 },
//                 option: function(data, escape) {
//                     if (data.customProperties) {
//                         return '<div><span class="dropdown-item-indicator">' + data.customProperties + '</span>' + escape(data.text) + '</div>';
//                     }
//                     return '<div>' + escape(data.text) + '</div>';
//                 }
//             }
//         });

//         // Evento para capturar mudanças no TomSelect
//         tomSelectInstance.on('change', function() {
//             resolveDataAssuntos(this.getValue());
//         });
//     }
// });

$("#make-headlines-select-assuntos-user").on("change", function(e){
    let option = $(this).val();

    let textAreaContainer = $(".text_area_values_assuntos");
    let textAreaExists = textAreaContainer.find("textarea[name='input_user']").length > 0;

    if(option == "all"){
        if (!textAreaExists) {
            textAreaContainer.append(`
                <div class="input_user_wrapper">
                    <label class="form-label">Sobre o que você deseja falar:</label>
                    <textarea name="input_user" rows="3" class="form-control mt-2" placeholder="Digite o assunto"></textarea>
                </div>
            `);
        }
    } else {
        textAreaContainer.find(".input_user_wrapper").remove();
    }
});


//  FUNCIONA PARA TONSELECT
// function resolveDataAssuntos(data) {
//     if (!Array.isArray(data)) {
//         data = [data]; // Garante que seja sempre um array
//     }

//     let textAreaContainer = $(".text_area_values_assuntos");
//     let textAreaExists = textAreaContainer.find("textarea[name='input_user']").length > 0;

//     if (data.includes("all")) {
//         if (!textAreaExists) {
//             textAreaContainer.append(`
//                 <div class="input_user_wrapper">
//                     <label class="form-label">Sobre o que você deseja falar:</label>
//                     <textarea name="input_user" rows="3" class="form-control mt-2" placeholder="Digite o assunto"></textarea>
//                 </div>
//             `);
//         }
//     } else {
//         textAreaContainer.find(".input_user_wrapper").remove();
//     }
// }

// ✅ Atualizado para remover tudo corretamente ao ocultar os inputs
// $("input[name=add_input]").change(function(e) {
//     let inputCLick = $(this).val();

//     if (inputCLick == 2) {
//         $(".exi_assuntos").removeClass("hidden");
//         $(".text_area_values_assuntos").removeClass("hidden");
//         $(".divVariables_id").addClass("hidden");

//     } else if (inputCLick == 1) {
//         $(".exi_assuntos").addClass("hidden");
//         $(".text_area_values_assuntos").addClass("hidden");
//         $(".text_area_values_assuntos").find(".input_user_wrapper").remove(); // Remove label + textarea
//         $(".divVariables_id").removeClass("hidden");
//     }

// });
$("input[name=who]").change(function(e) {
    let inputCLick = $(this).val();

    if (inputCLick == 'subject-moment') {
        $(".exi_assuntos").removeClass("hidden");
        $(".text_area_values_assuntos").removeClass("hidden");
        $(".divVariables_id").addClass("hidden");

    } else {
        $(".exi_assuntos").addClass("hidden");
        $(".text_area_values_assuntos").addClass("hidden");
        $(".text_area_values_assuntos").find(".input_user_wrapper").remove(); // Remove label + textarea
        $(".divVariables_id").removeClass("hidden");
    }

});

// Evento para carregar perguntas quando uma headline for selecionada
$(document).ready(function() {
    // Se existir o select de headlines
    if($('select#customer-headlines-select-headline').length > 0){
        $('select#customer-headlines-select-headline').on('change', function(){
            const headlineId = $(this).val();
            if(headlineId){
                getQuestions(headlineId);
            } else {
                $('#questions-container').hide();
            }
        });
    }

    // Se existir um select de headlines em formulários de roadmap
    if($('form#make_roadmap select#customer-headlines-select-headline').length > 0){
        $('form#make_roadmap select#customer-headlines-select-headline').on('change', function(){
            const headlineId = $(this).val();
            if(headlineId){
                getQuestions(headlineId);
            } else {
                $('#questions-container').hide();
            }
        });
    }
});

function getQuestions(headline_id){
    $.ajax({
        url: "/dashboard/user/headlines/favorites/get-questions",
        type: "POST",
        data: {
            headline_id: headline_id,
            _token: $('meta[name="csrf-token"]').attr('content')
        },
        success: function(response){
            if(response.success && response.questions.length > 0){
                // Criar HTML das perguntas
                let questionsHtml = `
                    <div class="mb-3">
                        <hr>
                        <label class="form-label">Responda as perguntas abaixo para otimizar o roteiro :</label>
                `;

                response.questions.forEach(function(question, index){
                    questionsHtml += `
                        <div class="mb-3">
                            <label class="form-label">${index + 1} - ${question.question}</label>
                            <input type="hidden" name="question_id[]" value="${question.question}">
                            <input type="text" class="form-control" name="questions[]" required placeholder="Digite sua resposta aqui...">
                        </div>
                    `;
                });

                questionsHtml += '</div>';

                // Inserir as perguntas no container
                $('#questions-container').html(questionsHtml);
                $('#questions-container').show();
            } else {
                $('#questions-container').hide();
                console.log('Nenhuma pergunta encontrada para esta headline');
            }
        },
        error: function(xhr){
            console.log('Erro ao carregar perguntas:', xhr.responseJSON?.message || 'Erro desconhecido');
            $('#questions-container').hide();
        }
    });
}


// document.addEventListener('DOMContentLoaded', function() {
//     const tx = document.getElementsByClassName('auto-resize');
//     for (let i = 0; i < tx.length; i++) {
//         tx[i].setAttribute('style', 'resize: none; overflow: hidden;');
//         tx[i].addEventListener("input", OnInput, false);
//     }

//     function OnInput() {
//         this.style.height = 'auto';
//         this.style.height = (this.scrollHeight) + 'px';
//     }
// });


// Verificar se deve abrir modal após reload da página
$(document).ready(function() {
    // Verificar se há dados de modal para abrir após reload
    const modalData = localStorage.getItem('openModalAfterReload');
    if (modalData) {
        try {
            const modalInfo = JSON.parse(modalData);

            // Aguardar um pouco para garantir que a página carregou completamente
            setTimeout(function() {
                // Abrir o modal específico
                if (modalInfo.modal === 'headlineCreatorModal') {
                    $('#headlineCreatorModal').modal('show');

                    // Se há dados específicos, você pode usá-los aqui
                    if (modalInfo.data && modalInfo.data.headline_id) {
                        // Exemplo: carregar dados da headline específica
                        console.log('Headline ID:', modalInfo.data.headline_id);
                        console.log('Status:', modalInfo.data.status);
                    }
                }

                // Limpar os dados do localStorage após usar
                localStorage.removeItem('openModalAfterReload');
            }, 500);

        } catch (e) {
            console.error('Erro ao processar dados do modal:', e);
            localStorage.removeItem('openModalAfterReload');
        }
    }
});

// Funções para auto-resize dos textareas
function adjustTextareaHeight(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = (textarea.scrollHeight) + 'px';
}

function adjustAllTextareas() {
    document.querySelectorAll('.auto-resize').forEach(function(textarea) {
        adjustTextareaHeight(textarea);
    });
}

const makeHeadlinesSelectVariablesUser = $('#make-headlines-select-variables-user');
if(makeHeadlinesSelectVariablesUser) makeHeadlinesSelectVariablesUser.on('change', function(){

    const variables = $(this).val() ?? [];

    if(!variables || !Array.isArray(variables)) return;
    $.ajax({
        url: "/dashboard/user/headlines/get-profile",
        type: "POST",
        data: {
            variable_selected: variables,
            _token: $('meta[name="csrf-token"]').attr('content')
        },
        success: function(response){
            if (!response.success) {
                // console.warn('Resposta sem success:', response);
                return;
            }

            
            if(variables.length > 0){
                $('#profile-reference-alert-me-public').removeClass('d-none');
            }else{
                $('#profile-reference-alert-me-public').addClass('d-none');
            }

            const profiles = response?.profiles || [];

            // Pega o elemento <select>
            const selectElement = document.getElementById('make-headlines-profiles-me-public');

            // Acessa a instância do TomSelect
            const ts = selectElement?.tomselect;

            if (!ts) {
                console.error('TomSelect não foi inicializado no elemento #make-headlines-profiles-me-public');
                return;
            }

            // 1. Limpa qualquer seleção atual (remove o que estava escolhido)
            ts.clear(true);  // true = silent (não dispara change)

            // 2. Limpa todas as opções antigas
            ts.clearOptions();

            // 3. Adiciona as novas opções
            if (profiles.length === 0) {
                ts.addOption({
                    value: '',
                    text: 'Nenhum perfil compatível encontrado',
                    disabled: true
                });
            } else {
                profiles.forEach(profile => {
                    ts.addOption({
                        value: profile.search_id,
                        text: profile.profile
                    });
                });
            }

            // 4. Atualiza o componente visualmente
            ts.refreshOptions(false);
        },
        error: function(xhr){
            
        }
    });
});