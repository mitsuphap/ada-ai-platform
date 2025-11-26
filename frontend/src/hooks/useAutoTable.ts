import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/axios'
import { PaginatedResponse } from '@/types/api'

export function useAutoTable(tableName: string, params?: {
  q?: string
  limit?: number
  offset?: number
  sort?: string
}) {
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['autoTable', tableName, params],
    queryFn: async () => {
      const { data } = await api.get<PaginatedResponse<any>>(`/auto/${tableName}`, { params })
      return data
    },
  })

  const createMutation = useMutation({
    mutationFn: async (item: any) => {
      const { data } = await api.post(`/auto/${tableName}`, item)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['autoTable', tableName] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, item }: { id: number; item: any }) => {
      const { data } = await api.put(`/auto/${tableName}/${id}`, item)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['autoTable', tableName] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/auto/${tableName}/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['autoTable', tableName] })
    },
  })

  return {
    data,
    isLoading,
    error,
    create: createMutation.mutate,
    update: updateMutation.mutate,
    remove: deleteMutation.mutate,
    isCreating: createMutation.isPending,
    isUpdating: updateMutation.isPending,
    isDeleting: deleteMutation.isPending,
  }
}

export function useAutoTableItem(tableName: string, id: number) {
  return useQuery({
    queryKey: ['autoTableItem', tableName, id],
    queryFn: async () => {
      const { data } = await api.get(`/auto/${tableName}/${id}`)
      return data
    },
    enabled: !!id,
  })
}

