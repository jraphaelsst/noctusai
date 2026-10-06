$('form#cores').submit(function (e) {
    "use strict";
    e.preventDefault();

    $('#button_core').prop('disabled', true);
    $('#button_core').text('Aguarde criando...');

    var formData = new FormData(this);

    $.ajax({
        type: "post",
        url: "/dashboard/user/cores/transcrible",
        data: formData,
        dataType: 'JSON',
        contentType: false,
        processData: false,
        success: function (data) {
             toastr[data.type](data.message);

            if (data.button) {
                $('#button_core').prop('disabled', false);
                $('#button_core').html('<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 5l0 14"/><path d="M5 12l14 0"/></svg>\n' +
                    '                            Criar Pesquisa');
            }
            if (data.redirect) {
                setTimeout(function () {
                    location.href = data.redirect;
                }, 1000);
            }
            if (data.refresh) {
                setTimeout(function () {
                    window.location.reload();
                }, 1000);
            }
            if (data.reset) {
                $('#customer-core')[0].reset();
                $('.j_option_text').fadeOut();
                $('.j_option_url').fadeIn();
                $('#modal-new-customer-core').modal('hide');
            }

        },
        error: function (data) {
            if (data.status === 422) { // Verifica se o status é 422 (Unprocessable Entity)
                setTimeout(function () {
                    toastr.error(data.responseJSON.message);
                }, 1500);
            } else {
                setTimeout(function () {
                    toastr.error('Ocorreu um erro ao criar a pesquisa.');
                }, 1500);
            }

            $('#button_core').prop('disabled', false);
            $('#button_core').html('<svg xmlns="http://www.w3.org/2000/svg" class="icon" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"/><path d="M12 5l0 14"/><path d="M5 12l14 0"/></svg>\n' +
                '                            Criar Pesquisa');
        }
    });
    return false;
});

$(document).on('click', '.j_core_view', function () {

    $('.j_customer_core_content').html('')
    var id = $(this).attr('id');

    $('#j_core_edit').text('');
    $('form#apply-customer-search input[name=customer_id]').val('');
    $('form#apply-customer-search input[name=customer_core_id]').val('');

    // //add data-id to reprocess headlines
    // $('.j_reprocess').attr('data-id', id)

    $.ajax({
        type: 'get',
        url: 'dashboard/user/cores/view/' + id,
        //data: {callback: 'Estrutura', callback_action: 'headline_gpt', id: id},
        dataType: 'json',
        success: function (data) {
            //EXIBE CALLBACKS
            if (data.success) {
                // Formata o JSON para uma string bem formatada
                console.log(data);
                $('#modal-view-search').modal('show')
                $('.j_customer_core_content').html(data.content)
                $('.j_reprocess').attr('data-id', id)

                $('form#apply-search input[name=core_id]').val(id);
            }
        }
    });

    $('.jwc_contact_modal_headlines_geradas').fadeIn(200);
    return false;
});

$(document).ready(function() {
    $('body').on('click', '.j_core_remove', function(e) {
        e.preventDefault(); // Previne comportamento padrão, se necessário

        $('#j_core_remove').modal('show'); 
        let id = $(this).attr('data-headline-id');   

        $(".j_core_remove_confirm").attr("data-headline-id", id); 
    });
});

$(document).on('click', '.j_core_remove_confirm', function () {
    let id = $(this).attr('data-headline-id');   
    $.ajax({
        type: 'get',
        url: 'dashboard/user/cores/remove/'+id,
        dataType: 'json',
        success: function (data) {
            if (data.success) {
                location.reload();
            }
        }
    });
    return false;
});
