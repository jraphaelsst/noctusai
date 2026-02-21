import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'

import { ClienteType } from '../pages/Clientes'
import { CondominioType } from '../pages/Condominios'
import { ImovelType } from '../pages/Imoveis'
import { PermutaImovelType, PermutaAutomovelType } from '../pages/Permutas'

const api = createApi({
  baseQuery: fetchBaseQuery({
    baseUrl: 'http://localhost:8000'
  }),
  endpoints: (builder) => ({
    getClientes: builder.query<ClienteType[], void>({
      query: () => 'proprietario'
    }),
    getCliente: builder.query<ClienteType, void>({
      query: (id) => `proprietario/${id}`
    }),
    getCondominios: builder.query<CondominioType[], void>({
      query: () => 'condominio'
    }),
    getCondominio: builder.query<CondominioType, void>({
      query: (id) => `condominio/${id}`
    }),
    getImoveis: builder.query<ImovelType[], void>({
      query: () => 'imovel'
    }),
    getImovel: builder.query<ImovelType, string>({
      query: (id) => `imovel/${id}`
    }),
    getPermutasImovel: builder.query<PermutaImovelType[], void>({
      query: () => 'permuta/imovel'
    }),
    getPermutaImovel: builder.query<PermutaImovelType, string>({
      query: (id) => `permuta/imovel/${id}`
    }),
    getPermutasAutomovel: builder.query<PermutaAutomovelType[], void>({
      query: () => 'permuta/automovel'
    }),
    getPermutaAutomovel: builder.query<PermutaAutomovelType, string>({
      query: (id) => `permuta/automovel/${id}`
    }),
    postNovoImovel: builder.mutation<unknown, ImovelType>({
      query: (body) => ({
        url: 'imovel',
        method: 'POST',
        body
      })
    }),
    postNovoCondominio: builder.mutation<unknown, CondominioType>({
      query: (body) => ({
        url: 'condominio',
        method: 'POST',
        body
      })
    }),
    postNovaPermutaImovel: builder.mutation<unknown, PermutaImovelType>({
      query: (body) => ({
        url: 'permuta/imovel',
        method: 'POST',
        body
      })
    }),
    postNovaPermutaAutomovel: builder.mutation<unknown, PermutaAutomovelType>({
      query: (body) => ({
        url: 'permuta/automovel',
        method: 'POST',
        body
      })
    }),
    postNovoCliente: builder.mutation<unknown, ClienteType>({
      query: (body) => ({
        url: 'proprietario',
        method: 'POST',
        body
      })
    })
  })
})

export const {
  useGetClientesQuery,
  useGetClienteQuery,
  useGetCondominiosQuery,
  useGetCondominioQuery,
  useGetImoveisQuery,
  useGetImovelQuery,
  useGetPermutasImovelQuery,
  useGetPermutaImovelQuery,
  useGetPermutasAutomovelQuery,
  useGetPermutaAutomovelQuery,
  usePostNovoImovelMutation,
  usePostNovoCondominioMutation,
  usePostNovaPermutaImovelMutation,
  usePostNovaPermutaAutomovelMutation,
  usePostNovoClienteMutation
} = api

export default api
