import { ChangeEvent, useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'

import { RootReducer } from '../../../store'

import { jwtDecode } from 'jwt-decode'
import swal from 'sweetalert2'
import useAxios from '../../../utils/useAxios'
import { getTipoImovel, getTipoAutomovel, getZona } from '../../../utils/typeLabels'
import { formatCurrency } from '../../../utils/formatCurrency'

import {
  openProp,
  closeProp
} from '../../../store/reducers/overlayProprietario'
import {
  openCondo,
  closeCondo
} from '../../../store/reducers/overlayCondominio'
import {
  openInteresses,
  closeInteresses,
  add,
  update,
  remove
} from '../../../store/reducers/overlayInteresses'

import Container from '../../../containers/Container'
import DropDown from '../../../components/DropDown'
import DropDownContainer from '../../../containers/DropDownContainer'

import {
  Form,
  FormField,
  FormInteresse,
  FormInput,
  FormLabel,
  Select,
  Table,
  TableCell,
  TableHead,
  TableRow,
  TableTitle,
  ActionIcon,
  ActionCell
} from './styles'
import Button from '../../../components/Button'
import OverlayPropForm from '../../../components/OverlayPropForm'
import OverlayCondoForm from '../../../components/OverlayCondoForm'
import OverlayInteressesForm from '../../../components/OverlayInteressesForm'

const NovoImovel = () => {
  const baseUrl = ''
  const api = useAxios()
  const dispatch = useDispatch()

  const { items } = useSelector((state: RootReducer) => state.overlayInteresses)

  const token = localStorage.getItem('authTokens')
  const decoded = jwtDecode(token!)
  const user_id = decoded.user_id

  const [imovelActive, setImovelActive] = useState(false)
  const [proprietarioActive, setProprietarioActive] = useState(false)
  const [interesseActive, setInteresseActive] = useState(false)
  const [condominioActive, setCondominioActive] = useState(false)

  const [ref, setRef] = useState('')
  const [corretor, setCorretor] = useState('')
  const [proprietario, setProprietario] = useState('')
  const [tipo, setTipo] = useState('')
  const [condominio, setCondominio] = useState('')
  const [valor, setValor] = useState('')

  const [nomeProprietario, setNomeProprietario] = useState('')
  const [corretorProprietario, setCorretorProprietario] = useState('')
  const [telefoneProprietario, setTelefoneProprietario] = useState('')
  const [emailProprietario, setEmailProprietario] = useState('')

  const [nomeCondominio, setNomeCondominio] = useState('')
  const [cep, setCep] = useState('')
  const [estado, setEstado] = useState('')
  const [cidade, setCidade] = useState('')
  const [bairro, setBairro] = useState('')
  const [rua, setRua] = useState('')
  const [numero, setNumero] = useState('')
  const [km, setKm] = useState('')
  const [valorCondominio, setValorCondominio] = useState('')

  const [tipoInteresse, setTipoInteresse] = useState('imovel')
  const [interesseImovel, setInteresseImovel] = useState({
    tipo: 'imovel',
    tipo_imovel: '',
    estado: '',
    zona: '',
    valor_minimo: 0,
    valor_maximo: 0
  })
  const [interesseAutomovel, setInteresseAutomovel] = useState({
    tipo: 'automovel',
    tipo_automovel: '',
    valor_minimo: 0,
    valor_maximo: 0
  })

  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [editingType, setEditingType] = useState<'imovel' | 'automovel' | null>(null)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editImovelData, setEditImovelData] = useState({
    tipo: 'imovel',
    tipo_imovel: '',
    estado: '',
    zona: '',
    valor_minimo: 0,
    valor_maximo: 0
  })
  const [editAutomovelData, setEditAutomovelData] = useState({
    tipo: 'automovel',
    tipo_automovel: '',
    valor_minimo: 0,
    valor_maximo: 0
  })

  // Manage Imóvel Dropdown
  useEffect(() => {
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
  }, [imovelActive])

  // Manage Proprietário Dropdown
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

  // Manage Interesses Dropdown
  useEffect(() => {
    const inteDropDownEl = document.getElementById('interesses-dropdown')
    const inteForm = document.getElementById('interesses-form')
    const inteInputFields = document.getElementsByClassName(
      'interesses-input-field'
    )

    const addClass = (el: HTMLElement, els: HTMLCollectionOf<Element>) => {
      el?.classList.add('active')
      for (let i = 0; i < els.length; i++) {
        els[i].classList.add('activeInput')
      }
    }

    const handleClick = () => {
      setInteresseActive(!interesseActive)
      interesseActive
        ? addClass(inteForm!, inteInputFields)
        : inteForm?.classList.remove('active')
    }
    inteDropDownEl?.addEventListener('click', handleClick)
    return () => {
      inteDropDownEl?.removeEventListener('click', handleClick)
    }
  }, [interesseActive])

  // Manage Condomínio Dropdown
  useEffect(() => {
    const condominioDropDownEl = document.getElementById('condominio-dropdown')
    const condominioForm = document.getElementById('condominio-form')
    const condominioInputFields = document.getElementsByClassName(
      'condominio-input-field'
    )

    const addClass = (el: HTMLElement, els: HTMLCollectionOf<Element>) => {
      el?.classList.add('active')
      for (let i = 0; i < els.length; i++) {
        els[i].classList.add('activeInput')
      }
    }

    const handleClick = () => {
      setCondominioActive(!condominioActive)
      condominioActive
        ? addClass(condominioForm!, condominioInputFields)
        : condominioForm?.classList.remove('active')
    }

    condominioDropDownEl?.addEventListener('click', handleClick)
    return () => {
      condominioDropDownEl?.removeEventListener('click', handleClick)
    }
  }, [condominioActive])

  // Abrir Proprietário Form Overlay
  const openPropForm = () => {
    dispatch(openProp())
  }

  const openCondoForm = () => {
    dispatch(openCondo())
  }

  const openInteressesForm = () => {
    dispatch(openInteresses())
  }

  // Cadastrar Proprietário
  useEffect(() => {
    const closePropForm = () => {
      dispatch(closeProp())
    }

    const botaoCadastrar = document.getElementById(
      'botao-cadastrar-proprietario'
    )
    const handleSubmit = () => {
      const formdata = new FormData()
      formdata.append('criado_por', user_id)
      formdata.append('nome', nomeProprietario)
      formdata.append('corretor', corretorProprietario)
      formdata.append('telefone', telefoneProprietario)
      formdata.append('email', emailProprietario)

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
          setCorretorProprietario('')
          setTelefoneProprietario('')
          setEmailProprietario('')
        }
        cadastrarProprietario()
        closePropForm()
      } catch (error) {
        console.log(error)
      }
    }

    if (botaoCadastrar) {
      botaoCadastrar.addEventListener('click', handleSubmit)
    }
    return () => {
      if (botaoCadastrar) {
        botaoCadastrar.removeEventListener('click', handleSubmit)
      }
    }
  }, [
    api,
    user_id,
    dispatch,
    nomeProprietario,
    corretorProprietario,
    telefoneProprietario,
    emailProprietario
  ])

  // Consulta CEP
  const consultaCep = () => {
    const limpa_formulario_cep = () => {
      // Rua
      setRua('')
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
        setRua('...')
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
                setRua(data.logradouro)
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

  // Cadastrar Condomínio
  useEffect(() => {
    const closeCondoForm = () => {
      dispatch(closeCondo())
    }

    const botaoCadastrar = document.getElementById('botao-cadastrar-condominio')
    const handleSubmit = async () => {
      const formdata = new FormData()
      formdata.append('criado_por', user_id)
      formdata.append('nome', nomeCondominio)
      formdata.append('cep', cep)
      formdata.append('estado', estado)
      formdata.append('cidade', cidade)
      formdata.append('bairro', bairro)
      formdata.append('endereco', rua)
      formdata.append('numero', numero)
      formdata.append('km', km)
      formdata.append('valor_condominio', valorCondominio)

      try {
        const cadastrarCondominio = async () => {
          const response = await api.post(baseUrl + '/condominio/', formdata)
          if (response.status === 201) {
            swal.fire({
              title: 'Condomínio criado com sucesso!',
              icon: 'success',
              toast: true,
              timer: 6000,
              position: 'top-right',
              timerProgressBar: true,
              showConfirmButton: false
            })
          } else {
            swal.fire({
              title: 'Houve algum erro, verifique os dados.',
              icon: 'error',
              toast: true,
              timer: 6000,
              position: 'top-right',
              timerProgressBar: true,
              showConfirmButton: false
            })
          }
          setNomeCondominio('')
          setCep('')
          setEstado('')
          setCidade('')
          setBairro('')
          setRua('')
          setNumero('')
          setKm('')
          setValorCondominio('')
        }
        cadastrarCondominio()
        closeCondoForm()
      } catch (error) {
        console.log(error)
      }
    }

    if (botaoCadastrar) {
      botaoCadastrar.addEventListener('click', handleSubmit)
    }
    return () => {
      if (botaoCadastrar) {
        botaoCadastrar.removeEventListener('click', handleSubmit)
      }
    }
  }, [
    api,
    dispatch,
    user_id,
    nomeCondominio,
    cep,
    estado,
    cidade,
    bairro,
    rua,
    numero,
    km,
    valorCondominio
  ])

  // Interesses Imóvel
  const handleTipoImovel = (e: ChangeEvent<HTMLInputElement>) => {
    setInteresseImovel({
      ...interesseImovel,
      tipo_imovel: e.target.value
    })
  }

  const handleEstado = (e: ChangeEvent<HTMLInputElement>) => {
    setInteresseImovel({
      ...interesseImovel,
      estado: e.target.value
    })
  }

  const handleZona = (e: ChangeEvent<HTMLInputElement>) => {
    setInteresseImovel({
      ...interesseImovel,
      zona: e.target.value
    })
  }

  const handleValorMinimoImovel = (e: ChangeEvent<HTMLInputElement>) => {
    setInteresseImovel({
      ...interesseImovel,
      valor_minimo: Number(e.target.value)
    })
  }

  const handleValorMaximoImovel = (e: ChangeEvent<HTMLInputElement>) => {
    setInteresseImovel({
      ...interesseImovel,
      valor_maximo: Number(e.target.value)
    })
  }

  // Interesses Automóvel
  const handleTipoAutomovel = (e: ChangeEvent<HTMLInputElement>) => {
    setInteresseAutomovel({
      ...interesseAutomovel,
      tipo_automovel: e.target.value
    })
  }

  const handleValorMinimoAutomovel = (e: ChangeEvent<HTMLInputElement>) => {
    setInteresseAutomovel({
      ...interesseAutomovel,
      valor_minimo: Number(e.target.value)
    })
  }

  const handleValorMaximoAutomovel = (e: ChangeEvent<HTMLInputElement>) => {
    setInteresseAutomovel({
      ...interesseAutomovel,
      valor_maximo: Number(e.target.value)
    })
  }

  // Adicionar Interesse
  const addInteresse = () => {
    if (tipoInteresse === 'imovel') {
      dispatch(add(interesseImovel))
      dispatch(closeInteresses())
    } else {
      dispatch(add(interesseAutomovel))
      dispatch(closeInteresses())
    }
  }

  const imoveisInteresses = items.filter((item) => item.tipo === 'imovel')
  const automoveisInteresses = items.filter((item) => item.tipo === 'automovel')

  const handleEditInteresse = (index: number, type: 'imovel' | 'automovel') => {
    const allItems = type === 'imovel' ? imoveisInteresses : automoveisInteresses
    const item = allItems[index]
    const globalIndex = items.findIndex((i) => i === item)
    
    setEditingIndex(globalIndex)
    setEditingType(type)
    
    if (type === 'imovel') {
      setEditImovelData({
        tipo: 'imovel',
        tipo_imovel: item.tipo_imovel || '',
        estado: item.estado || '',
        zona: item.zona || '',
        valor_minimo: item.valor_minimo,
        valor_maximo: item.valor_maximo
      })
    } else {
      setEditAutomovelData({
        tipo: 'automovel',
        tipo_automovel: item.tipo_automovel || '',
        valor_minimo: item.valor_minimo,
        valor_maximo: item.valor_maximo
      })
    }
    setEditModalOpen(true)
  }

  const handleSaveEdit = () => {
    if (editingIndex === null || editingType === null) return
    
    if (editingType === 'imovel') {
      dispatch(update({ index: editingIndex, item: editImovelData }))
    } else {
      dispatch(update({ index: editingIndex, item: editAutomovelData }))
    }
    
    setEditModalOpen(false)
    setEditingIndex(null)
    setEditingType(null)
  }

  const handleDeleteInteresse = (index: number, type: 'imovel' | 'automovel') => {
    const allItems = type === 'imovel' ? imoveisInteresses : automoveisInteresses
    const item = allItems[index]
    const globalIndex = items.findIndex((i) => i === item)
    
    swal.fire({
      title: 'Remover interesse?',
      text: 'Esta ação não pode ser desfeita.',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#E17055',
      cancelButtonColor: '#636E72',
      confirmButtonText: 'Sim, remover',
      cancelButtonText: 'Cancelar'
    }).then((result) => {
      if (result.isConfirmed) {
        dispatch(remove(globalIndex))
        swal.fire({
          title: 'Removido!',
          text: 'O interesse foi removido.',
          icon: 'success',
          toast: true,
          timer: 3000,
          position: 'top-right',
          showConfirmButton: false
        })
      }
    })
  }

  // Cadastrar Imóvel
  useEffect(() => {
    const botaoCadastrar = document.getElementById('botao-cadastrar-imovel')
    const handleSubmit = async () => {
      const formdata = new FormData()
      formdata.append('criado_por', user_id)
      formdata.append('ref', ref)
      formdata.append('corretor', corretor)
      formdata.append('tipo', tipo)
      formdata.append('proprietario', proprietario)
      formdata.append('condominio', condominio)
      formdata.append('interesses_imoveis', JSON.stringify(imoveisInteresses))
      formdata.append(
        'interesses_automoveis',
        JSON.stringify(automoveisInteresses)
      )
      formdata.append('valor_venda', valor)

      try {
        const cadastrarimovel = async () => {
          const response = await api.post(baseUrl + '/imovel/', formdata)
          if (response.status === 201) {
            swal.fire({
              title: 'Imóvel criado com sucesso!',
              icon: 'success',
              toast: true,
              timer: 6000,
              position: 'top-right',
              timerProgressBar: true,
              showConfirmButton: false
            })
          }
          setRef('')
          setCorretor('')
          setTipo('')
          setProprietario('')
          setCondominio('')
          setValor('')
        }
        cadastrarimovel()
      } catch (error) {
        console.log(error)
      }
    }

    if (botaoCadastrar) {
      botaoCadastrar.addEventListener('click', handleSubmit)
    }
    return () => {
      if (botaoCadastrar) {
        botaoCadastrar.removeEventListener('click', handleSubmit)
      }
    }
  }, [
    api,
    user_id,
    ref,
    corretor,
    tipo,
    proprietario,
    condominio,
    imoveisInteresses,
    automoveisInteresses,
    items,
    valor
  ])

  return (
    <>
      <Container title="Novo Imóvel">
        <DropDownContainer>
          <div>
            <DropDown id="imovel-dropdown" title="Imóvel" />
            <Form id="imovel-form" className="">
              <FormField className="imovel-input-field">
                <FormLabel>Ref:</FormLabel>
                <FormInput
                  onChange={(e) => setRef(e.target.value)}
                  value={ref}
                  type="text"
                />
              </FormField>
              <FormField className="imovel-input-field">
                <FormLabel>Condomínio:</FormLabel>
                <FormInput
                  onChange={(e) => setCondominio(e.target.value)}
                  value={condominio}
                  type="text"
                />
                <i
                  onClick={openCondoForm}
                  className="fa-solid fa-plus"
                  style={{ marginLeft: '4px', cursor: 'pointer' }}
                />
              </FormField>
              <FormField className="imovel-input-field">
                <FormLabel>Tipo:</FormLabel>
                <FormInput
                  onChange={(e) => setTipo(e.target.value)}
                  value={tipo}
                  type="text"
                />
              </FormField>
              <FormField className="imovel-input-field">
                <FormLabel>Corretor:</FormLabel>
                <FormInput
                  onChange={(e) => setCorretor(e.target.value)}
                  value={corretor}
                  type="text"
                />
              </FormField>
              <FormField className="imovel-input-field">
                <FormLabel>Valor de Venda:</FormLabel>
                <FormInput
                  onChange={(e) => setValor(e.target.value)}
                  value={valor}
                  type="text"
                />
              </FormField>
            </Form>
          </div>
          <div>
            <DropDown id="proprietario-dropdown" title="Proprietário" />
            <Form id="proprietario-form" className="">
              <FormField className="proprietario-input-field">
                <FormLabel>Nome:</FormLabel>
                <FormInput
                  onChange={(e) => setProprietario(e.target.value)}
                  value={proprietario}
                  type="text"
                />
                <i
                  onClick={openPropForm}
                  className="fa-solid fa-plus"
                  style={{ marginLeft: '4px', cursor: 'pointer' }}
                />
              </FormField>
              <FormField className="proprietario-input-field">
                <FormLabel>Tel Contato:</FormLabel>
                <FormInput type="number" />
              </FormField>
              <FormField className="proprietario-input-field">
                <FormLabel>Email:</FormLabel>
                <FormInput type="email" />
              </FormField>
            </Form>
          </div>
          <div>
            <DropDown id="interesses-dropdown" title="Interesses" />
            <FormInteresse id="interesses-form" className="">
              {imoveisInteresses.length > 0 ? (
                <>
                  <TableTitle>Imóveis</TableTitle>
                  <Table>
                    <thead>
                      <TableRow>
                        <TableHead>Tipo de Imóvel</TableHead>
                        <TableHead>Estado</TableHead>
                        <TableHead>Zona</TableHead>
                        <TableHead>Valor Mínimo</TableHead>
                        <TableHead>Valor Máximo</TableHead>
                        <TableHead style={{ textAlign: 'center' }}>Ações</TableHead>
                      </TableRow>
                    </thead>
                    <tbody>
                      {imoveisInteresses.map((item, index) => (
                        <TableRow key={index}>
                          <TableCell>{getTipoImovel(item.tipo_imovel || '')}</TableCell>
                          <TableCell>{item.estado}</TableCell>
                          <TableCell>{getZona(item.zona || '')}</TableCell>
                          <TableCell>{formatCurrency(item.valor_minimo)}</TableCell>
                          <TableCell>{formatCurrency(item.valor_maximo)}</TableCell>
                          <ActionCell>
                            <ActionIcon
                              type="button"
                              title="Editar"
                              onClick={() => handleEditInteresse(index, 'imovel')}
                            >
                              <i className="fa-solid fa-pen" />
                            </ActionIcon>
                            <ActionIcon
                              type="button"
                              className="delete"
                              title="Remover"
                              onClick={() => handleDeleteInteresse(index, 'imovel')}
                            >
                              <i className="fa-solid fa-trash" />
                            </ActionIcon>
                          </ActionCell>
                        </TableRow>
                      ))}
                    </tbody>
                  </Table>
                </>
              ) : (
                <div>Sem interesses imóveis cadastrados</div>
              )}
              {automoveisInteresses.length > 0 ? (
                <>
                  <TableTitle>Automóveis</TableTitle>
                  <Table>
                    <thead>
                      <TableRow>
                        <TableHead>Tipo de Automóvel</TableHead>
                        <TableHead>Valor Mínimo</TableHead>
                        <TableHead>Valor Máximo</TableHead>
                        <TableHead style={{ textAlign: 'center' }}>Ações</TableHead>
                      </TableRow>
                    </thead>
                    <tbody>
                      {automoveisInteresses.map((item, index) => (
                        <TableRow key={index}>
                          <TableCell>{getTipoAutomovel(item.tipo_automovel || '')}</TableCell>
                          <TableCell>{formatCurrency(item.valor_minimo)}</TableCell>
                          <TableCell>{formatCurrency(item.valor_maximo)}</TableCell>
                          <ActionCell>
                            <ActionIcon
                              type="button"
                              title="Editar"
                              onClick={() => handleEditInteresse(index, 'automovel')}
                            >
                              <i className="fa-solid fa-pen" />
                            </ActionIcon>
                            <ActionIcon
                              type="button"
                              className="delete"
                              title="Remover"
                              onClick={() => handleDeleteInteresse(index, 'automovel')}
                            >
                              <i className="fa-solid fa-trash" />
                            </ActionIcon>
                          </ActionCell>
                        </TableRow>
                      ))}
                    </tbody>
                  </Table>
                </>
              ) : (
                <div>Sem interesses automóveis cadastrados</div>
              )}
              <p>
                Adicionar Novo Interesse
                <i
                  onClick={openInteressesForm}
                  className="fa-solid fa-plus"
                  style={{ marginLeft: '4px', cursor: 'pointer' }}
                />
              </p>
            </FormInteresse>
          </div>
          <Button id="botao-cadastrar-imovel" type="button">
            Cadastrar
          </Button>
        </DropDownContainer>
      </Container>
      <OverlayPropForm title="Novo Proprietário">
        <FormField className="proprietario-input-field">
          <FormLabel>Nome:</FormLabel>
          <FormInput
            onChange={(e) => setNomeProprietario(e.target.value)}
            value={nomeProprietario}
            type="text"
          />
        </FormField>
        <FormField className="proprietario-input-field">
          <FormLabel>Corretor:</FormLabel>
          <FormInput
            onChange={(e) => setCorretorProprietario(e.target.value)}
            value={corretorProprietario}
            type="text"
          />
        </FormField>
        <FormField className="proprietario-input-field">
          <FormLabel>Telefone:</FormLabel>
          <FormInput
            onChange={(e) => setTelefoneProprietario(e.target.value)}
            value={telefoneProprietario}
            type="text"
          />
        </FormField>
        <FormField className="proprietario-input-field">
          <FormLabel>Email:</FormLabel>
          <FormInput
            onChange={(e) => setEmailProprietario(e.target.value)}
            value={emailProprietario}
            type="email"
          />
        </FormField>
        <Button id="botao-cadastrar-proprietario" type="button">
          Cadastrar
        </Button>
      </OverlayPropForm>
      <OverlayCondoForm title="Novo Condomínio">
        <FormField className="condominio-input-field">
          <FormLabel>Nome:</FormLabel>
          <FormInput
            onChange={(e) => {
              setNomeCondominio(e.target.value)
            }}
            value={nomeCondominio}
            type="text"
          />
        </FormField>
        <FormField className="condominio-input-field">
          <FormLabel>Cep:</FormLabel>
          <FormInput
            type="text"
            onChange={(e) => {
              setCep(e.target.value)
            }}
            onBlur={consultaCep}
            value={cep}
          />
        </FormField>
        <FormField className="condominio-input-field">
          <FormLabel>Estado:</FormLabel>
          <FormInput
            onChange={(e) => {
              setEstado(e.target.value)
            }}
            value={estado}
            type="text"
          />
        </FormField>
        <FormField className="condominio-input-field">
          <FormLabel>Cidade:</FormLabel>
          <FormInput
            onChange={(e) => {
              setCidade(e.target.value)
            }}
            value={cidade}
            type="text"
          />
        </FormField>
        <FormField className="condominio-input-field">
          <FormLabel>Bairro:</FormLabel>
          <FormInput
            onChange={(e) => {
              setBairro(e.target.value)
            }}
            value={bairro}
            type="text"
          />
        </FormField>
        <FormField className="condominio-input-field">
          <FormLabel>Endereço:</FormLabel>
          <FormInput
            onChange={(e) => {
              setRua(e.target.value)
            }}
            value={rua}
            type="text"
          />
        </FormField>
        <FormField className="condominio-input-field">
          <FormLabel>Número:</FormLabel>
          <FormInput
            onChange={(e) => {
              setNumero(e.target.value)
            }}
            value={numero}
            type="text"
          />
        </FormField>
        <FormField className="condominio-input-field">
          <FormLabel>Km Raposo:</FormLabel>
          <FormInput
            onChange={(e) => {
              setKm(e.target.value)
            }}
            value={km}
            type="text"
          />
        </FormField>
        <FormField className="condominio-input-field">
          <FormLabel>Valor:</FormLabel>
          <FormInput
            onChange={(e) => {
              setValorCondominio(e.target.value)
            }}
            value={valorCondominio}
            type="number"
          />
        </FormField>
        <Button id="botao-cadastrar-condominio" type="button">
          Cadastrar
        </Button>
      </OverlayCondoForm>
      <OverlayInteressesForm title="Novo Interesse">
        <FormField className="interesses-input-field">
          <FormLabel>Tipo:</FormLabel>
          <div>
            <Select
              onChange={(e) => {
                setTipoInteresse(e.target.value)
              }}
            >
              <option value="imovel">Imóvel</option>
              <option value="automovel">Automóvel</option>
            </Select>
          </div>
        </FormField>
        {tipoInteresse === 'imovel' ? (
          <>
            <FormField className="interesses-input-field">
              <FormLabel>Tipo de Imóvel:</FormLabel>
              <FormInput
                onChange={handleTipoImovel}
                value={interesseImovel.tipo_imovel}
                type="text"
              />
            </FormField>
            <FormField className="interesses-input-field">
              <FormLabel>Estado:</FormLabel>
              <FormInput
                onChange={handleEstado}
                value={interesseImovel.estado}
                type="text"
              />
            </FormField>
            <FormField className="interesses-input-field">
              <FormLabel>Zona:</FormLabel>
              <FormInput
                onChange={handleZona}
                value={interesseImovel.zona}
                type="text"
              />
            </FormField>
            <FormField className="interesses-input-field">
              <FormLabel>Valor Mínimo:</FormLabel>
              <FormInput
                onChange={handleValorMinimoImovel}
                value={interesseImovel.valor_minimo}
                type="number"
              />
            </FormField>
            <FormField className="interesses-input-field">
              <FormLabel>Valor Máximo:</FormLabel>
              <FormInput
                onChange={handleValorMaximoImovel}
                value={interesseImovel.valor_maximo}
                type="number"
              />
            </FormField>
          </>
        ) : (
          <>
            <FormField className="interesses-input-field">
              <FormLabel>Tipo de Automóvel:</FormLabel>
              <FormInput
                onChange={handleTipoAutomovel}
                value={interesseAutomovel.tipo_automovel}
                type="text"
              />
            </FormField>
            <FormField className="interesses-input-field">
              <FormLabel>Valor Mínimo:</FormLabel>
              <FormInput
                onChange={handleValorMinimoAutomovel}
                value={interesseAutomovel.valor_minimo}
                type="text"
              />
            </FormField>
            <FormField className="interesses-input-field">
              <FormLabel>Valor Máximo:</FormLabel>
              <FormInput
                onChange={handleValorMaximoAutomovel}
                value={interesseAutomovel.valor_maximo}
                type="text"
              />
            </FormField>
          </>
        )}
        <Button onClick={addInteresse} type="button">
          Cadastrar
        </Button>
      </OverlayInteressesForm>

      {editModalOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000
          }}
          onClick={() => setEditModalOpen(false)}
        >
          <div
            style={{
              background: '#fff',
              padding: '24px',
              borderRadius: '2px',
              width: '100%',
              maxWidth: '500px',
              border: '1px solid #DFE6E9'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginBottom: '16px', color: '#2D3436' }}>
              Editar Interesse {editingType === 'imovel' ? 'Imóvel' : 'Automóvel'}
            </h3>
            
            {editingType === 'imovel' ? (
              <>
                <FormField style={{ marginBottom: '12px' }}>
                  <FormLabel>Tipo de Imóvel:</FormLabel>
                  <FormInput
                    value={editImovelData.tipo_imovel}
                    onChange={(e) => setEditImovelData({ ...editImovelData, tipo_imovel: e.target.value })}
                    type="text"
                  />
                </FormField>
                <FormField style={{ marginBottom: '12px' }}>
                  <FormLabel>Estado:</FormLabel>
                  <FormInput
                    value={editImovelData.estado}
                    onChange={(e) => setEditImovelData({ ...editImovelData, estado: e.target.value })}
                    type="text"
                  />
                </FormField>
                <FormField style={{ marginBottom: '12px' }}>
                  <FormLabel>Zona:</FormLabel>
                  <FormInput
                    value={editImovelData.zona}
                    onChange={(e) => setEditImovelData({ ...editImovelData, zona: e.target.value })}
                    type="text"
                  />
                </FormField>
                <FormField style={{ marginBottom: '12px' }}>
                  <FormLabel>Valor Mínimo:</FormLabel>
                  <FormInput
                    value={editImovelData.valor_minimo}
                    onChange={(e) => setEditImovelData({ ...editImovelData, valor_minimo: Number(e.target.value) })}
                    type="number"
                  />
                </FormField>
                <FormField style={{ marginBottom: '12px' }}>
                  <FormLabel>Valor Máximo:</FormLabel>
                  <FormInput
                    value={editImovelData.valor_maximo}
                    onChange={(e) => setEditImovelData({ ...editImovelData, valor_maximo: Number(e.target.value) })}
                    type="number"
                  />
                </FormField>
              </>
            ) : (
              <>
                <FormField style={{ marginBottom: '12px' }}>
                  <FormLabel>Tipo de Automóvel:</FormLabel>
                  <FormInput
                    value={editAutomovelData.tipo_automovel}
                    onChange={(e) => setEditAutomovelData({ ...editAutomovelData, tipo_automovel: e.target.value })}
                    type="text"
                  />
                </FormField>
                <FormField style={{ marginBottom: '12px' }}>
                  <FormLabel>Valor Mínimo:</FormLabel>
                  <FormInput
                    value={editAutomovelData.valor_minimo}
                    onChange={(e) => setEditAutomovelData({ ...editAutomovelData, valor_minimo: Number(e.target.value) })}
                    type="number"
                  />
                </FormField>
                <FormField style={{ marginBottom: '12px' }}>
                  <FormLabel>Valor Máximo:</FormLabel>
                  <FormInput
                    value={editAutomovelData.valor_maximo}
                    onChange={(e) => setEditAutomovelData({ ...editAutomovelData, valor_maximo: Number(e.target.value) })}
                    type="number"
                  />
                </FormField>
              </>
            )}
            
            <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
              <Button type="button" onClick={handleSaveEdit}>
                Salvar
              </Button>
              <button
                type="button"
                onClick={() => setEditModalOpen(false)}
                style={{
                  padding: '10px 20px',
                  border: '1px solid #DFE6E9',
                  background: '#fff',
                  color: '#636E72',
                  cursor: 'pointer'
                }}
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default NovoImovel
