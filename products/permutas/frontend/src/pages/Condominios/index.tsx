import { useState, useEffect, useCallback, useRef } from 'react'
import { formatCurrency } from '../../utils/formatCurrency'
import { useNavigate } from 'react-router-dom'
import swal from 'sweetalert2'
import Container from '../../containers/Container'
import Modal from '../../components/Modal'
import CondominioForm from '../../components/ModalForms/CondominioForm'
import DataTable, { Column } from '../../components/DataTable'
import Button from '../../components/Button'
import Pagination from '../../components/Pagination'
import useAxios from '../../utils/useAxios'

export type CondominioType = {
  id: number
  criado_por: string
  nome: string
  cep: string
  estado: string
  cidade: string
  bairro: string
  endereco: string
  numero: number
  km: number
  valor_condominio: number
}

type PaginatedResponse<T> = {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

const Condominios = () => {
  const [condominios, setCondominios] = useState<CondominioType[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingCondominio, setEditingCondominio] = useState<CondominioType | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [serverFilters, setServerFilters] = useState<Record<string, string>>({})
  const navigate = useNavigate()
  const api = useAxios()
  const filtersRef = useRef(serverFilters)
  filtersRef.current = serverFilters

  const fetchCondominios = useCallback(async (page: number = 1, filters: Record<string, string> = {}) => {
    setIsLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('page', String(page))
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value)
      })
      const response = await api.get(`/condominio/?${params.toString()}`)
      const data = response.data as PaginatedResponse<CondominioType>
      if (data.results) {
        if (data.results.length === 0 && page > 1) {
          setCurrentPage(page - 1)
          return
        }
        setCondominios(data.results)
        setTotalCount(data.count)
        setTotalPages(Math.ceil(data.count / 10) || 1)
      } else {
        setCondominios(Array.isArray(response.data) ? response.data : [])
      }
    } catch (error: any) {
      if (error?.response?.status === 404 && page > 1) {
        setCurrentPage(page - 1)
        return
      }
      console.error('Error fetching condominios:', error)
      setCondominios([])
    } finally {
      setIsLoading(false)
    }
  }, [api])

  useEffect(() => {
    fetchCondominios(currentPage, filtersRef.current)
  }, [currentPage])

  const handleServerFilter = useCallback((filters: Record<string, string>) => {
    setServerFilters(filters)
    setCurrentPage(1)
    fetchCondominios(1, filters)
  }, [fetchCondominios])

  const columns: Column<CondominioType>[] = [
    { key: 'nome', label: 'Nome', filterable: true, filterKey: 'nome' },
    { key: 'bairro', label: 'Bairro', filterable: true, filterKey: 'bairro' },
    { key: 'cidade', label: 'Cidade', filterable: true, filterKey: 'cidade' },
    { key: 'endereco', label: 'Endereço' },
    { 
      key: 'valor_condominio', 
      label: 'Valor Cond.',
      render: (item) => formatCurrency(item.valor_condominio)
    },
  ]

  const handleView = (condominio: CondominioType) => {
    navigate(`/condominio/${condominio.id}`)
  }

  const handleDelete = async (condominio: CondominioType) => {
    try {
      await api.delete(`/condominio/${condominio.id}/`)
      swal.fire('Sucesso', 'Condomínio excluído com sucesso!', 'success')
      fetchCondominios(currentPage, serverFilters)
    } catch (error) {
      swal.fire('Erro', 'Não foi possível excluir o condomínio.', 'error')
    }
  }

  const handleCloseModal = () => {
    setIsModalOpen(false)
    setEditingCondominio(null)
  }

  return (
    <Container title="Condomínios">
      <Button type="button" onClick={() => setIsModalOpen(true)}>
        Cadastrar Novo
      </Button>

      <DataTable
        data={condominios || []}
        columns={columns}
        onView={handleView}
        onEdit={(condominio) => {
          setEditingCondominio(condominio)
          setIsModalOpen(true)
        }}
        onDelete={handleDelete}
        deleteConfirmMessage="Tem certeza que deseja excluir este condomínio?"
        loading={isLoading}
        serverFiltering={true}
        onServerFilter={handleServerFilter}
        totalCount={totalCount}
      />

      <Pagination
        currentPage={currentPage}
        totalPages={totalPages}
        totalCount={totalCount}
        onPageChange={setCurrentPage}
      />

      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={editingCondominio ? 'Editar Condomínio' : 'Novo Condomínio'}
      >
        <CondominioForm
          onSuccess={() => {
            fetchCondominios(currentPage, serverFilters)
            handleCloseModal()
          }}
          onClose={handleCloseModal}
          initialData={editingCondominio}
        />
      </Modal>
    </Container>
  )
}

export default Condominios
