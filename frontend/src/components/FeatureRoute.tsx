import { Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

interface FeatureRouteProps {
  feature: string;
  children: React.ReactNode;
}

export const FeatureRoute: React.FC<FeatureRouteProps> = ({ feature, children }) => {
  const { hasFeature, loading } = useAuth();

  if (loading) {
    return null;
  }

  if (!hasFeature(feature)) {
    return <Navigate to="/404" replace />;
  }

  return <>{children}</>;
};
