
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
        