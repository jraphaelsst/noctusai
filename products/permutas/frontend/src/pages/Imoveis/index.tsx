import { useState, useEffect, useCallback, useRef } from 'react'
import { formatCurrency } from '../../utils/formatCurrency'
import { useNavigate } from 'react-router-dom'
import swal from 'sweetalert2'
import Container from '../../containers/Container'
import Modal from '../../components/Modal'
import ImovelForm from '../../components/ModalForms/ImovelForm'
import DataTable, { Column } from '../../components/DataTable'
import Button from '../../components/Button'
import Pagination from '../../components/Pagination'
import useAxios from '../../utils/useAxios'

export type ImovelType = {
  id: number
  criado_por: string
  corretor: string
  tipo: number | null
  tipo_nome: string | null
  zona: number | null
  zona_nome: string | null
  proprietario_nome: string
  proprietario_telefone: string
  proprietario_email: string
  ref: string
  condominio_nome: string
  condominio_bairro: string
  condominio_km: string
  condominio_endereco: string
  valor_venda: number
  interesses_imoveis: string
  interesses_automoveis: string
}

type PaginatedResponse<T> = {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

const Imoveis = () => {
  const [imoveis, setImoveis] = useState<ImovelType[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingImovel, setEditingImovel] = useState<ImovelType | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [serverFilters, setServerFilters] = useState<Record<string, string>>({})
  const navigate = useNavigate()
  const api = useAxios()
  const filtersRef = useRef(serverFilters)
  filtersRef.current = serverFilters

  const fetchImoveis = useCallback(async (page: number = 1, filters: Record<string, string> = {}) => {
    setIsLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('page', String(page))
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value)
      })
      const response = await api.get(`/imovel/?${params.toString()}`)
      const data = response.data as PaginatedResponse<ImovelType>
      if (data.results) {
        if (data.results.length === 0 && page > 1) {
          setCurrentPage(page - 1)
          return
        }
        setImoveis(data.results)
        setTotalCount(data.count)
        setTotalPages(Math.ceil(data.count / 10) || 1)
      } else {
        setImoveis(Array.isArray(response.data) ? response.data : [])
      }
    } catch (error: any) {
      if (error?.response?.status === 404 && page > 1) {
        setCurrentPage(page - 1)
        return
      }
      console.error('Error fetching imoveis:', error)
      setImoveis([])
    } finally {
      setIsLoading(false)
    }
  }, [api])

  useEffect(() => {
    fetchImoveis(currentPage, filtersRef.current)
  }, [currentPage])

  const handlePageChange = (page: number) => {
    setCurrentPage(page)
  }

  const handleServerFilter = useCallback((filters: Record<string, string>) => {
    setServerFilters(filters)
    setCurrentPage(1)
    fetchImoveis(1, filters)
  }, [fetchImoveis])

  const columns: Column<ImovelType>[] = [
    { key: 'ref', label: 'Referência', filterable: true, filterKey: 'ref' },
    { key: 'corretor', label: 'Corretor', filterable: true, filterKey: 'corretor' },
    { 
      key: 'tipo', 
      label: 'Tipo',
      filterable: true,
      filterKey: 'tipo_nome',
      render: (item) => item.tipo_nome || '-'
    },
    { 
      key: 'zona', 
      label: 'Zona',
      filterable: true,
      filterKey: 'zona_nome',
      render: (item) => item.zona_nome || '-'
    },
    { key: 'condominio_nome', label: 'Condomínio', filterable: true, filterKey: 'condominio' },
    { key: 'proprietario_nome', label: 'Proprietário', filterable: true, filterKey: 'proprietario' },
    { 
      key: 'valor_venda', 
      label: 'Valor',
      render: (item) => formatCurrency(item.valor_venda)
    },
  ]

  const handleView = (imovel: ImovelType) => {
    navigate(`/imovel/${imovel.id}`)
  }

  const handleDelete = async (imovel: ImovelType) => {
    try {
      await api.delete(`/imovel/${imovel.id}/`)
      swal.fire('Sucesso', 'Imóvel excluído com sucesso!', 'success')
      fetchImoveis(currentPage, serverFilters)
    } catch (error) {
      swal.fire('Erro', 'Não foi possível excluir o imóvel.', 'error')
    }
  }

  const handleCloseModal = () => {
    setIsModalOpen(false)
    setEditingImovel(null)
  }

  return (
    <Container title="Imóveis">
      <Button type="button" onClick={() => setIsModalOpen(true)}>
        Cadastrar Novo
      </Button>

      <DataTable
        data={imoveis || []}
        columns={columns}
        onView={handleView}
        onEdit={(imovel) => {
          setEditingImovel(imovel)
          setIsModalOpen(true)
        }}
        onDelete={handleDelete}
        deleteConfirmMessage="Tem certeza que deseja excluir este imóvel?"
        loading={isLoading}
        serverFiltering={true}
        onServerFilter={handleServerFilter}
        totalCount={totalCount}
      />

      <Pagination
        currentPage={currentPage}
        totalPages={totalPages}
        totalCount={totalCount}
        onPageChange={handlePageChange}
      />

      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={editingImovel ? 'Editar Imóvel' : 'Novo Imóvel'}
      >
        <ImovelForm
          onSuccess={() => {
            fetchImoveis(currentPage, serverFilters)
            handleCloseModal()
          }}
          onClose={handleCloseModal}
          initialData={editingImovel}
        />
      </Modal>
    </Container>
  )
}

export default Imoveis
