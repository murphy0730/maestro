import { useQuery } from '@tanstack/react-query';
import { listSkills } from './skills';
export const useSkills = () => useQuery({ queryKey: ['skills'], queryFn: listSkills });
