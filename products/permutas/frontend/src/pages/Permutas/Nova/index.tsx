import { useEffect, useState } from 'react'

import { jwtDecode } from 'jwt-decode'
import swal from 'sweetalert2'

import useAxios from '../../../utils/useAxios'

import Container from '../../../containers/Container'
import DropDown from '../../../components/DropDown'
import DropDownContainer from '../../../containers/DropDownContainer'

import Button from '../../../components/Button'
import { Form, FormField, FormInput, FormLabel, Label, Select } from './styles'

const NovaPermuta = () => {
  const baseUrl = ''
  const api = useAxios()

  // Coletar Usuário Logado
  const token = localStorage.getItem('authTokens')
  const decoded = jwtDecode(token!)
  const user_id = decoded.user_id

  // Gerenciamento de Estado Ativo
  const [imovelActive, setImovelActive] = useState(false)
  const [automovelActive, setAutomovelActive] = useState(false)
  const [proprietarioActive, setProprietarioActive] = useState(false)

  // Tipo de Permuta
  const [tipoPermuta, setTipoPermuta] = useState('imovel')

  // Gerenciamento de Estados de Proprietário
  const [proprietario, setProprietario] = useState('')

  const [nomeProprietario, setNomeProprietario] = useState('')
  const [telefoneProprietario, setTelefoneProprietario] = useState('')
  const [emailProprietario, setEmailProprietario] = useState('')
  const [atendidoPor, setAtendidoPor] = useState('')

  // Estados conforme Tipo de Permuta
  //// Imóvel
  const [corretorImovel, setCorretorImovel] = useState('')
  // const [proprietarioImovel, setProprietarioImovel] = useState('')
  const [tipoImovel, setTipoImovel] = useState('')
  const [condominio, setCondominio] = useState('')
  const [zona, setZona] = useState('')
  const [cep, setCep] = useState('')
  const [estado, setEstado] = useState('')
  const [cidade, setCidade] = useState('')
  const [bairro, setBairro] = useState('')
  const [endereco, setEndereco] = useState('')
  const [numero, setNumero] = useState('')
  const [valorImovel, setValorImovel] = useState('')

  //// Automóvel
  const [corretorAutomovel, setCorretorAutomovel] = useState('')
  // const [proprietarioAutomovel, setProprietarioAutomovel] = useState('')
  const [tipoAutomovel, setTipoAutomovel] = useState('')
  const [marca, setMarca] = useState('')
  const [modelo, setModelo] = useState('')
  const [motor, setMotor] = useState('')
  const [valorAutomovel, setValorAutomovel] = useState('')

  // Toggle Imóvel/Automóvel DropDown
  useEffect(() => {
    if (tipoPermuta === 'imovel') {
      const imovelDropDownEl = document.getElementById('imovel-dropdown')
      const imovelForm = document.getElementById('imovel-form')
      const imovelInputFields =
        document.getElementsByClassName('imovel-input-field')

      const addClass = (el: HTMLElement, els: HTMLCollectionOf<Element>) => {
        el?.classList.add('active')
        for (let i = 0; i < els.length; i++) {
          els[i].classList.add('activeInput')
        }
      }

      const handleClick = () => {
        setImovelActive(!imovelActive)
        imovelActive
          ? addClass(imovelForm!, imovelInputFields)
          : imovelForm?.classList.remove('active')
      }
      imovelDropDownEl?.addEventListener('click', handleClick)
      return () => {
        imovelDropDownEl?.removeEventListener('click', handleClick)
      }
    } else {
      const automovelDropDownEl = document.getElementById('automovel-dropdown')
      const automovelForm = document.getElementById('automovel-form')
      const automovelInputFields = document.getElementsByClassName(
        'automovel-input-field'
      )

      const addClass = (el: HTMLElement, els: HTMLCollectionOf<Element>) => {
        el?.classList.add('active')
        for (let i = 0; i < els.length; i++) {
          els[i].classList.add('activeInput')
        }
      }

      const handleClick = () => {
        setAutomovelActive(!automovelActive)
        automovelActive
          ? addClass(automovelForm!, automovelInputFields)
          : automovelForm?.classList.remove('active')
      }
      automovelDropDownEl?.addEventListener('click', handleClick)
      return () => {
        automovelDropDownEl?.removeEventListener('click', handleClick)
      }
    }
  }, [tipoPermuta, imovelActive, automovelActive])

  // Toggle Proprietário DropDown
  useEffect(() => {
    const propDropDownEl = document.getElementById('proprietario-dropdown')
    const propForm = document.getElementById('proprietario-form')
    const propInputFields = document.getElementsByClassName(
      'proprietario-input-field'
    )

    const addClass = (el: HTMLElement, els: HTMLCollectionOf<Element>) => {
      el?.classList.add('active')
      for (let i = 0; i < els.length; i++) {
        els[i].classList.add('activeInput')
      }
    }

    const handleClick = () => {
      setProprietarioActive(!proprietarioActive)
      proprietarioActive
        ? addClass(propForm!, propInputFields)
        : propForm?.classList.remove('active')
    }
    propDropDownEl?.addEventListener('click', handleClick)
    return () => {
      propDropDownEl?.removeEventListener('click', handleClick)
    }
  }, [proprietarioActive])

  // Consultar CEP
  const consultaCep = () => {
    const limpa_formulario_cep = () => {
      // Rua
      setEndereco('')
      // Bairro
      setBairro('')
      // Cidade
      setCidade('')
      // Estado
      setEstado('')
    }
    // Checa se o valor de CEP não é nulo
    if (cep != '') {
      // Testa a formatação do CEP
      const validacep = /^[0-9]{8}$/
      if (validacep.test(cep)) {
        // Preenche os valores dos campos com "..." enquanto aguarda resposta da API
        // Rua
        setEndereco('...')
        // Bairro
        setBairro('...')
        // Cidade
        setCidade('...')
        // Estado
        setEstado('...')

        // Consulta o webservice viacep.com.br
        const fetchCep = async (cep: string) => {
          await fetch('https://viacep.com.br/ws/' + cep + '/json/?callback=', {
            method: 'GET'
          }).then((response: Response) => {
            if (!('erro' in response)) {
              response.json().then((data) => {
                setEndereco(data.logradouro)
                setBairro(data.bairro)
                setCidade(data.localidade)
                setEstado(data.uf)
              })
            } else {
              limpa_formulario_cep()
              alert('CEP não encontrado.')
            }
          })
        }
        fetchCep(cep)
      } else {
        limpa_formulario_cep()
        alert('Formato de CEP inválido.')
      }
    } else {
      limpa_formulario_cep()
    }
  }

  // Cadastrar Proprietário
  useEffect(() => {
    const botaoCadastrarProprietario = document.getElementById('')
    const handleSubmit = () => {
      const formdata = new FormData()
      formdata.append('criado_por', user_id)
      formdata.append('nome', nomeProprietario)
      formdata.append('telefone', telefoneProprietario)
      formdata.append('email', emailProprietario)
      formdata.append('atendido_por', atendidoPor)

      try {
        const cadastrarProprietario = async () => {
          const response = await api.post(baseUrl + '/proprietario/', formdata)
          if (response.status === 201) {
            swal.fire({
              title: 'Proprietário cadastrado com sucesso!',
              icon: 'success',
              toast: true,
              timer: 6000,
              position: 'top-right',
              timerProgressBar: true,
              showConfirmButton: false
            })
          }
          setNomeProprietario('')
          setTelefoneProprietario('')
          setEmailProprietario('')
          setAtendidoPor('')
        }
        cadastrarProprietario()
      } catch (error) {
        console.log(error)
      }
    }

    if (botaoCadastrarProprietario) {
      botaoCadastrarProprietario.addEventListener('click', handleSubmit)
    }
    return () => {
      if (botaoCadastrarProprietario) {
        botaoCadastrarProprietario.removeEventListener('click', handleSubmit)
      }
    }
  }, [
    api,
    user_id,
    nomeProprietario,
    telefoneProprietario,
    emailProprietario,
    atendidoPor
  ])

  // Cadastrar Permuta
  useEffect(() => {
    const botaoCadastrarPermuta = document.getElementById(
      'botao-cadastrar-permuta'
    )
    const handleSubmit = async () => {
      if (tipoPermuta === 'imovel') {
        const formdata = new FormData()
        formdata.append('criado_por', user_id)
        formdata.append('corretor', corretorImovel)
        formdata.append('tipo', tipoImovel)
        formdata.append('condominio', condominio)
        formdata.append('zona', zona)
        formdata.append('cep', cep)
        formdata.append('estado', estado)
        formdata.append('cidade', cidade)
        formdata.append('bairro', bairro)
        formdata.append('endereco', endereco)
        formdata.append('numero', numero)
        formdata.append('valor', valorImovel)
        formdata.append('proprietario', proprietario)

        try {
          const cadastrarPermutaImovel = async () => {
            const response = await api.post(
              baseUrl + '/permuta/imovel/',
              formdata
            )
            if (response.status === 201) {
              swal.fire({
                title: 'Permuta Imóvel criada com sucesso!',
                icon: 'success',
                toast: true,
                timer: 6000,
                position: 'top-right',
                timerProgressBar: true,
                showConfirmButton: false
              })
            }
            setCorretorImovel('')
            setProprietario('')
            setTipoImovel('')
            setCondominio('')
            setZona('')
            setCep('')
            setEstado('')
            setCidade('')
            setBairro('')
            setEndereco('')
            setNumero('')
            setValorImovel('')
          }
          cadastrarPermutaImovel()
        } catch (error) {
          console.log(error)
        }
      } else {
        const formdata = new FormData()
        formdata.append('criado_por', user_id)
        // formdata.append('proprietario', proprietarioMovel)
        formdata.append('corretor', corretorAutomovel)
        formdata.append('tipo', tipoAutomovel)
        formdata.append('marca', marca)
        formdata.append('modelo', modelo)
        formdata.append('motor', motor)
        formdata.append('valor', valorAutomovel)
        formdata.append('proprietario', proprietario)

        try {
          const cadastrarPermutaAutomovel = async () => {
            const response = await api.post(
              baseUrl + '/permuta/automovel/',
              formdata
            )
            if (response.status === 201) {
              swal.fire({
                title: 'Permuta Automóvel criada com sucesso!',
                icon: 'success',
                toast: true,
                timer: 6000,
                position: 'top-right',
                timerProgressBar: true,
                showConfirmButton: false
              })
            }
            setCorretorAutomovel('')
            setProprietario('')
            setTipoAutomovel('')
            setMarca('')
            setModelo('')
            setMotor('')
            setValorAutomovel('')
          }
          cadastrarPermutaAutomovel()
        } catch (error) {
          console.log(error)
        }
      }
    }

    if (botaoCadastrarPermuta) {
      botaoCadastrarPermuta.addEventListener('click', handleSubmit)
    }
    return () => {
      if (botaoCadastrarPermuta) {
        botaoCadastrarPermuta.removeEventListener('click', handleSubmit)
      }
    }
  }, [
    user_id,
    proprietario,
    api,
    bairro,
    estado,
    cidade,
    cep,
    condominio,
    corretorImovel,
    corretorAutomovel,
    endereco,
    marca,
    modelo,
    motor,
    valorImovel,
    valorAutomovel,
    numero,
    tipoImovel,
    tipoAutomovel,
    zona,
    tipoPermuta
  ])

  return (
    <Container title="Nova Permuta">
      <DropDownContainer>
        <div>
          <Label>Selecione o tipo:</Label>
          <Select
            onChange={(e) => {
              setTipoPermuta(e.target.value)
            }}
            value={tipoPermuta}
          >
            <option value="imovel">Imóvel</option>
            <option value="automovel">Automóvel</option>
          </Select>
        </div>
        {tipoPermuta === 'imovel' ? (
          <>
            <div>
              <DropDown id="imovel-dropdown" title="Imóvel" />
              <Form id="imovel-form" className="">
                <FormField className="imovel-input-field">
                  <FormLabel>Corretor:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setCorretorImovel(e.target.value)
                    }}
                    value={corretorImovel}
                    type="text"
                  />
                </FormField>
                <FormField className="imovel-input-field">
                  <FormLabel>Tipo:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setTipoImovel(e.target.value)
                    }}
                    value={tipoImovel}
                    type="text"
                  />
                </FormField>
                <FormField className="imovel-input-field">
                  <FormLabel>Condomínio:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setCondominio(e.target.value)
                    }}
                    value={condominio}
                    type="text"
                  />
                </FormField>
                <FormField className="imovel-input-field">
                  <FormLabel>Zona:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setZona(e.target.value)
                    }}
                    value={zona}
                    type="text"
                  />
                </FormField>
                <FormField className="imovel-input-field">
                  <FormLabel>CEP:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setCep(e.target.value)
                    }}
                    onBlur={consultaCep}
                    value={cep}
                    type="text"
                  />
                </FormField>
                <FormField className="imovel-input-field">
                  <FormLabel>Estado:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setEstado(e.target.value)
                    }}
                    value={estado}
                    type="text"
                  />
                </FormField>
                <FormField className="imovel-input-field">
                  <FormLabel>Cidade:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setCidade(e.target.value)
                    }}
                    value={cidade}
                    type="text"
                  />
                </FormField>
                <FormField className="imovel-input-field">
                  <FormLabel>Bairro:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setBairro(e.target.value)
                    }}
                    value={bairro}
                    type="text"
                  />
                </FormField>
                <FormField className="imovel-input-field">
                  <FormLabel>Endereço:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setEndereco(e.target.value)
                    }}
                    value={endereco}
                    type="text"
                  />
                </FormField>
                <FormField className="imovel-input-field">
                  <FormLabel>Numero:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setNumero(e.target.value)
                    }}
                    value={numero}
                    type="text"
                  />
                </FormField>
                <FormField className="imovel-input-field">
                  <FormLabel>Valor:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setValorImovel(e.target.value)
                    }}
                    value={valorImovel}
                    type="text"
                  />
                </FormField>
              </Form>
            </div>
          </>
        ) : (
          <>
            <div>
              <DropDown id="automovel-dropdown" title="Automóvel" />
              <Form id="automovel-form" className="">
                <FormField className="automovel-input-field">
                  <FormLabel>Corretor:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setCorretorAutomovel(e.target.value)
                    }}
                    value={corretorAutomovel}
                    type="text"
                  />
                </FormField>
                <FormField className="automovel-input-field">
                  <FormLabel>Tipo:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setTipoAutomovel(e.target.value)
                    }}
                    value={tipoAutomovel}
                    type="text"
                  />
                </FormField>
                <FormField className="automovel-input-field">
                  <FormLabel>Marca:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setMarca(e.target.value)
                    }}
                    value={marca}
                    type="text"
                  />
                </FormField>
                <FormField className="automovel-input-field">
                  <FormLabel>Modelo:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setModelo(e.target.value)
                    }}
                    value={modelo}
                    type="text"
                  />
                </FormField>
                <FormField className="automovel-input-field">
                  <FormLabel>Motor:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setMotor(e.target.value)
                    }}
                    value={motor}
                    type="text"
                  />
                </FormField>
                <FormField className="automovel-input-field">
                  <FormLabel>Valor:</FormLabel>
                  <FormInput
                    onChange={(e) => {
                      setValorAutomovel(e.target.value)
                    }}
                    value={valorAutomovel}
                    type="text"
                  />
                </FormField>
              </Form>
            </div>
          </>
        )}
        <div>
          <DropDown id="proprietario-dropdown" title="Proprietário" />
          <Form id="proprietario-form" className="">
            <FormField className="proprietario-input-field">
              <FormLabel>Nome:</FormLabel>
              <FormInput
                onChange={(e) => {
                  setProprietario(e.target.value)
                }}
                value={proprietario}
                type="text"
              />
            </FormField>
          </Form>
        </div>
        <Button id="botao-cadastrar-permuta" type="button">
          Cadastrar
        </Button>
      </DropDownContainer>
    </Container>
  )
}

export default NovaPermuta
