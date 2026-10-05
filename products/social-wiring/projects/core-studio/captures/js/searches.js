$('form#save-variables').submit(function (e){
    "use strict";

    e.preventDefault();

    $('#button_save_variables').disabled = true;
    $('#button_save_variables').text('Aguarde salvando...');

    var formData = new FormData(this);

    $.ajax({
        type: "post",
        url: "/dashboard/user/searches/save",
        data: formData,
        contentType: false,
        processData: false,
        success: function(data){
            toastr.success('Perfil atualizado. Redirecionando...')
            setTimeout(function(){
                window.location.reload();
            }, 1000);
        },
        error: function(data){
            if (data.status === 422) { // Verifica se o status é 422 (Unprocessable Entity)
                var errors = data.responseJSON.errors;
                $.each(errors, function(index, value) {
                    toastr.error(value);
                    console.error(value);
                });
            } else {
                toastr.error('Ocorreu um erro ao salvar o perfil.');
            }

            $('#button_save_variables').disabled = false;
            $('#button_save_variables').text('Salvar');
        }
    });
    return false;
})
 
$(document).ready(function() {
    $('body').on('click', '.j_search_remove:not(.viral-topic-remove-btn)', function(e) {
        e.preventDefault(); // Previne comportamento padrão, se necessário

        $('#j_search_remove').modal('show'); 
        let id = $(this).attr('data-headline-id');   

        $(".j_search_remove_confirm").attr("data-headline-id", id); 
    });
});

$(document).on('click', '.j_search_remove_confirm', function () {
    let id = $(this).attr('data-headline-id');   
    $.ajax({
        type: 'get',
        url: 'dashboard/user/searches/remove/'+id,
        dataType: 'json',
        success: function (data) {
            if (data.success) {
                location.reload();
            }
        }
    });
    return false;
});

$('form#searches').submit(function (e) {
    "use strict";
    e.preventDefault();

    $('#button_search').prop('disabled', true);
    $('#button_search').text('Aguarde criando...');

    var formData = new FormData(this);

    $.ajax({
        type: "post",
        url: "/dashboard/user/searches/store",
        data: formData,
        // dataType: 'JSON',
        contentType: false,
        processData: false,
        success: function(data){
            toastr[data.type](data.message);

            if(data.button){
                $('#button_search').prop('disabled', false);
                $('#button_search').html('<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 5l0 14"/><path d="M5 12l14 0"/></svg>\n'+
                    '                            Criar Pesquisa');
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
            if(data.reset){
                $('#customer-search')[0].reset();
                $('.j_option_text').fadeOut();
                $('.j_option_url').fadeIn();
                $('#modal-new-customer-search').modal('hide');
            }

        },
        error: function(data) {
            if (data.status === 422) { // Verifica se o status é 422 (Unprocessable Entity)
                var errors = data.responseJSON.errors;
                $.each(errors, function(index, value) {
                    toastr.error(value);
                    console.error(value);
                });
            } else {
                toastr.error('Ocorreu um erro ao criar a pesquisa.');
            }

            $('#button_search').prop('disabled', false);
            $('#button_search').html('<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 5l0 14"/><path d="M5 12l14 0"/></svg>\n'+
                '                            Criar Pesquisa');
        }
    });
    return false;
});

$(document).on('click', '.j_search_view', function () {

    $('.j_customer_search_data_gpt').html('')
    $('.j_customer_search_content').html('')
    var id = $(this).attr('id');

    $('#j_search_edit').text('');
    $('form#apply-customer-search input[name=customer_id]').val('');
    $('form#apply-customer-search input[name=customer_search_id]').val('');

    // //add data-id to reprocess headlines
    // $('.j_reprocess').attr('data-id', id)

    $.ajax({
        type: 'get',
        url: 'dashboard/user/searches/view/'+id,
        //data: {callback: 'Estrutura', callback_action: 'headline_gpt', id: id},
        dataType: 'json',
        success: function (data) {
            //EXIBE CALLBACKS
            if (data.success) {
                // Formata o JSON para uma string bem formatada

                $('#modal-view-search').modal('show')
                $('.j_customer_search_data_gpt').html(data.data_gpt)
                $('.j_customer_search_content').html(data.content)
                $('.j_reprocess').attr('data-id', id)

                var formattedText = data.data_gpt_edit.replace(/<br\s*\/?>/gi, "\n");
                $('#j_search_edit').text(formattedText);

                $('form#apply-search input[name=search_id]').val(id);
            }
        }
    });

    $('.jwc_contact_modal_headlines_geradas').fadeIn(200);
    return false;
});

$('form#apply-search').submit(function (e) {
    "use strict";
    e.preventDefault();

    $('#apply_customer_search_button').prop('disabled', true);
    $('#apply_customer_search_button').text('Aguarde salvando...');

    var formData = new FormData(this);

    let searchId = $('form#apply-search input[name=search_id]').val();
    let search = $('#j_search_edit').val();

    // Adiciona o valor de customerSearch ao FormData com o índice "customer_search"
    formData.append('search', search);
    formData.append('search_id', searchId);
    
    $.ajax({
        type: "post",
        url: "/dashboard/user/searches/variables/apply",
        data: formData,
        // dataType: 'JSON',
        contentType: false,
        processData: false,
        success: function(data){
            toastr[data.type](data.message);

            if(data.button){
                $('#apply_customer_search_button_confirm').prop('disabled', false);
                $('#apply_customer_search_button_confirm').html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                    '                            Aplicar Pesquisa');
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
            if(data.reset){
                $('#customer-search')[0].reset();
                $('.j_option_text').fadeOut();
                $('.j_option_url').fadeIn();
                $('#modal-new-customer-search').modal('hide');
            }

        },
        error: function(data) {
            if (data.status === 422) { // Verifica se o status é 422 (Unprocessable Entity)
                var errors = data.responseJSON.errors;
                $.each(errors, function(index, value) {
                    toastr.error(value);
                    console.error(value);
                });
            } else {
                toastr.error('Ocorreu um erro ao salvar a pesquisa.');
            }

            $('#apply_customer_search_button').prop('disabled', false);
            $('#apply_customer_search_button').html('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon icon-tabler icons-tabler-outline icon-tabler-circle-dashed-check"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M8.56 3.69a9 9 0 0 0 -2.92 1.95"></path><path d="M3.69 8.56a9 9 0 0 0 -.69 3.44"></path><path d="M3.69 15.44a9 9 0 0 0 1.95 2.92"></path><path d="M8.56 20.31a9 9 0 0 0 3.44 .69"></path><path d="M15.44 20.31a9 9 0 0 0 2.92 -1.95"></path><path d="M20.31 15.44a9 9 0 0 0 .69 -3.44"></path><path d="M20.31 8.56a9 9 0 0 0 -1.95 -2.92"></path><path d="M15.44 3.69a9 9 0 0 0 -3.44 -.69"></path><path d="M9 12l2 2l4 -4"></path></svg>\n'+
                '                            Aplicar Pesquisa');
        }
    });

    return false;
});

document.addEventListener("DOMContentLoaded", function () {
    var el = document.getElementById('make-searches-select-type');
    if (el) {
        new TomSelect(el, {
            copyClassesToDropdown: false,
            dropdownParent: 'body',
            controlInput: '<input>',
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

$('.j_option_extract').on('change', function(){
    if($(this).val() == 'transcribe_only' || $(this).val() == 'transcribe_extract' || $(this).val() == 'instagram_comments' || $(this).val() == 'youtube_comments' ){
        $('.j_option_url').fadeIn();
        $('.j_option_text').fadeOut(); 
    }else{
        $('.j_option_url').fadeOut();
        $('.j_option_text').fadeIn();
    }
    //Adicionar mais Url
    if($(this).val() == 'youtube_comments'){
        $('.j_more_url').fadeIn()
        $('.transcreve_extrai_div').css('display', 'none');
    }else{
        $('.j_more_url').fadeOut()
        $('.transcreve_extrai_div').css('display', 'block');
    }
})


window.updateHiddenField = function() {
    const badges = document.querySelectorAll('.viral-topic-badge, .viral-topic-badge-manual');
    const topics = Array.from(badges).map(badge => badge.dataset.topic);
    const hiddenField = document.getElementById('subject_viral_hidden');
    
    // console.log('Atualizando campo hidden:', {
    //     badges: badges.length,
    //     topics: topics,
    //     hiddenField: !!hiddenField
    // });
    
    if (hiddenField) {
        hiddenField.value = topics.join('\n');
        // console.log('Campo hidden atualizado com valor:', hiddenField.value);
    }
};

// Permitir adicionar tópico com Enter
document.addEventListener('DOMContentLoaded', function() {
    const input = document.getElementById('new-viral-topic');
    if (input) {
        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                window.addViralTopic();
            }
        });
        
        // Atualizar campo hidden quando a página carrega
        window.updateHiddenField();
    }
    
    // Atualizar campo hidden também quando a página carrega (garantir que funcione)
    setTimeout(function() {
        window.updateHiddenField();
    }, 100);
});

// Gerenciamento de abas com URL
document.addEventListener('DOMContentLoaded', function() {
    // Função para atualizar a URL sem recarregar a página
    function updateURL(tab) {
        const url = new URL(window.location);
        if (tab === 'me') {
            url.searchParams.delete('tab');
        } else {
            url.searchParams.set('tab', tab);
        }
        window.history.pushState({}, '', url);
    }

    // Função para ativar uma aba específica
    function activateTab(tabName) {
        // Remover classe active de todas as abas e painéis
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.remove('active', 'show');
        });

        // Ativar a aba e painel correspondentes
        const tabLink = document.querySelector(`[data-tab="${tabName}"]`);
        const tabPane = document.getElementById(tabName);
        
        if (tabLink && tabPane) {
            tabLink.classList.add('active');
            tabPane.classList.add('active', 'show');
        }
    }

    // Verificar parâmetro da URL ao carregar a página
    const urlParams = new URLSearchParams(window.location.search);
    const activeTab = urlParams.get('tab') || null;

    if(activeTab) activateTab(activeTab);

    // Adicionar event listeners para as abas
    document.querySelectorAll('[data-tab]').forEach(tabLink => {
        tabLink.addEventListener('click', function(e) {
            e.preventDefault();
            const tabName = this.getAttribute('data-tab');
            activateTab(tabName);
            updateURL(tabName);
        });
    });

    // Interceptar mudanças no histórico do navegador (botão voltar/avançar)
    window.addEventListener('popstate', function(e) {
        const urlParams = new URLSearchParams(window.location.search);
        const activeTab = urlParams.get('tab') || 'my-research';
        activateTab(activeTab);
    });
});