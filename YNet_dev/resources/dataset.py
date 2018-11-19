import csv

from .imports import *
from .torch_imports import *
from .core import *
from .transforms import *
from .layer_optimizer import *
from .dataloader import DataLoader
from collections import Counter

# (!) added imports to allow open_image to function with skimage.io.imread(), file-extension agnostic.
from skimage.external import tifffile
# (!) added for debug
import matplotlib.pyplot as plt



def get_cv_idxs(n, cv_idx=0, val_pct=0.2, seed=42):
    """ Get a list of index values for Validation set from a dataset
    
    Arguments:
        n : int, Total number of elements in the data set.
        cv_idx : int, starting index [idx_start = cv_idx*int(val_pct*n)] 
        val_pct : (int, float), validation set percentage 
        seed : seed value for RandomState
        
    Returns:
        list of indexes 
    """
    np.random.seed(seed)
    n_val = int(val_pct * n)
    idx_start = cv_idx * n_val
    idxs = np.random.permutation(n)
    return idxs[idx_start:idx_start + n_val]


def resize_img(fname, targ, path, new_path):
    """
    Enlarge or shrink a single image to scale, such that the smaller of the height or width dimension is equal to targ.
    """
    dest = os.path.join(path, new_path, str(targ), fname)
    if os.path.exists(dest): return
    im = Image.open(os.path.join(path, fname)).convert(
        'RGB')  # (!) Calls PIL module with option to convert to RGB!! probably causes issues!
    r, c = im.size
    ratio = targ / min(r, c)
    sz = (scale_to(r, ratio, targ), scale_to(c, ratio, targ))
    os.makedirs(os.path.split(dest)[0], exist_ok=True)
    im.resize(sz, Image.LINEAR).save(dest)


def resize_imgs(fnames, targ, path, new_path):
    """
    Enlarge or shrink a set of images in the same directory to scale, such that the smaller of the height or width dimension is equal to targ.
    Note: 
    -- This function is multithreaded for efficiency. 
    -- When destination file or folder already exist, function exists without raising an error. 
    """
    if not os.path.exists(os.path.join(path, new_path, str(targ), fnames[0])):
        with ThreadPoolExecutor(8) as e:
            ims = e.map(lambda x: resize_img(x, targ, path, new_path), fnames)
            for x in tqdm(ims, total=len(fnames), leave=False): pass
    return os.path.join(path, new_path, str(targ))


def read_dir(path, folder):
    """ Returns a list of relative file paths to `path` for all files within `folder` """
    full_path = os.path.join(path, folder)
    fnames = glob(f"{full_path}/*.*")
    if any(fnames):
        return [os.path.relpath(f, path) for f in fnames]
    else:
        raise FileNotFoundError("{} folder doesn't exist or is empty".format(folder))


def read_dirs(path, folder):
    '''
    Fetches name of all files in path in long form, and labels associated by extrapolation of directory names. 
    '''
    lbls, fnames, all_lbls = [], [], []
    full_path = os.path.join(path, folder)
    for lbl in sorted(os.listdir(full_path)):
        if lbl not in ('.ipynb_checkpoints', '.DS_Store'):
            all_lbls.append(lbl)
            for fname in os.listdir(os.path.join(full_path, lbl)):
                if fname not in ('.DS_Store'):
                    fnames.append(os.path.join(folder, lbl, fname))
                    lbls.append(lbl)
    return fnames, lbls, all_lbls


def n_hot(ids, c):
    '''
    one hot encoding by index. Returns array of length c, where all entries are 0, except for the indecies in ids
    '''
    res = np.zeros((c,), dtype=np.float32)
    res[ids] = 1
    return res


def folder_source(path, folder, d):
    """
    Returns the filenames and labels for a folder within a path
    (!) Modified to accomodate multiple source folders for a single class e.g. WT from Experiment 01 and 02

    Returns:
    -------
    fnames: a list of the filenames within `folder`
    cls_idx_arr: a numpy array of the label indices in `u_classes` (indices per unique classes)
    u_classes: a list of unique classes (e.g. genotypes) present in all_lbls
    src_idx_arr: a numpy array of the label indices in 'all_lbls' (indices per labels in 'folder'), useful for normalization.
    all_lbls: a list of all of the labels in `folder`, where the # of labels is determined by the # of directories within `folder`
    
    """
    fnames, lbls, all_lbls = read_dirs(path, folder)
    
    lbls2classes = {l: l.split('_')[1] for l in all_lbls} # (!) dict mapping lbls (folders) to classes (genotype)
    u_classes = list(dict.fromkeys(list(lbls2classes.values()))) # (!) get unique classes
    
    if d == {}:
        d_cls = {label: idx for idx, label in enumerate(u_classes)}
        d_src = {label_: idx_ for idx_, label_ in enumerate(all_lbls)}

        # (!) populating d with lbls: class, class_idx   
        for key, value in lbls2classes.items():
            d[key] = [d_src[key], d_cls[value], lbls2classes[key]]

    src_idxs  = [d[lbl][0] for lbl in lbls] # (!) using d to generate class-lables for each image
    cls_idxs  = [d[lbl][1] for lbl in lbls] # (!) using d to generate source-lables (which dataset) for each image

    src_idx_arr = np.array(src_idxs, dtype=int)
    cls_idx_arr = np.array(cls_idxs, dtype=int)
    
    # temp = [idxs.index(i) for i in range(len(all_lbls))]
    # for ii in temp: print(f"{idxs[ii]} maps to {fnames[ii]}")
    
    return fnames, cls_idx_arr, u_classes, src_idx_arr, all_lbls

def parse_csv_labels(fn, skip_header=True, cat_separator=' '):
    """Parse filenames and label sets from a CSV file.

    This method expects that the csv file at path :fn: has two columns. If it
    has a header, :skip_header: should be set to True. The labels in the
    label set are expected to be space separated.

    Arguments:
        fn: Path to a CSV file.
        skip_header: A boolean flag indicating whether to skip the header.

    Returns:
        a four-tuple of (
            sorted image filenames,
            a dictionary of filenames and corresponding labels,
            a sorted set of unique labels,
            a dictionary of labels to their corresponding index, which will
            be one-hot encoded.
        )
    .
    :param cat_separator: the separator for the categories column
    """
    df = pd.read_csv(fn, index_col=0, header=0 if skip_header else None, dtype=str)
    fnames = df.index.values
    df.iloc[:, 0] = df.iloc[:, 0].str.split(cat_separator)
    return sorted(fnames), list(df.to_dict().values())[0]


def nhot_labels(label2idx, csv_labels, fnames, c):
    all_idx = {k: n_hot([label2idx[o] for o in v], c)
               for k, v in csv_labels.items()}
    return np.stack([all_idx[o] for o in fnames])


def csv_source(folder, csv_file, skip_header=True, suffix='', continuous=False):
    fnames, csv_labels = parse_csv_labels(csv_file, skip_header)
    return dict_source(folder, fnames, csv_labels, suffix, continuous)


def dict_source(folder, fnames, csv_labels, suffix='', continuous=False):
    all_labels = sorted(list(set(p for o in csv_labels.values() for p in o)))
    full_names = [os.path.join(folder, str(fn) + suffix) for fn in fnames]
    if continuous:
        label_arr = np.array([np.array(csv_labels[i]).astype(np.float32)
                              for i in fnames])
    else:
        label2idx = {v: k for k, v in enumerate(all_labels)}
        label_arr = nhot_labels(label2idx, csv_labels, fnames, len(all_labels))
        is_single = np.all(label_arr.sum(axis=1) == 1)
        if is_single: label_arr = np.argmax(label_arr, axis=1)
    return full_names, label_arr, all_labels


class BaseDataset(Dataset):
    """An abstract class representing a fastai dataset, it extends torch.utils.data.Dataset."""

    def __init__(self, transform=None):
        self.transform = transform
        self.n = self.get_n()
        self.c = self.get_c()
        self.sz = self.get_sz()

    def get1item(self, idx):
        # x, y = self.get_x(idx), self.get_y(idx)
        # return self.get(self.transform, x, y)
        x, y, src_idx = self.get_x(idx), self.get_y(idx), self.get_src_idx(idx) #(!) src_idx
        return self.get(self.transform, x, y, src_idx) #(!) src_idx       

    def __getitem__(self, idx):
        # if isinstance(idx, slice):
        #     xs, ys = zip(*[self.get1item(i) for i in range(*idx.indices(self.n))])
        #     return np.stack(xs), ys
        # return self.get1item(idx)
        if isinstance(idx, slice):
            xs, ys, src_idxs = zip(*[self.get1item(i) for i in range(*idx.indices(self.n))]) #(!) src_idx
            return np.stack(xs), ys, src_idxs #(!) src_idx
        return self.get1item(idx)        

    def __len__(self):
        return self.n

    def get(self, tfm, x, y, src_idx):
        # return (x, y) if tfm is None else tfm(x, y)
        return (x, y, src_idx) if tfm is None else tfm(x, y, src_idx) # (!) finally calling tfm functions. (!) src_idx      

    @abstractmethod
    def get_n(self):
        """Return number of elements in the dataset == len(self)."""
        raise NotImplementedError

    @abstractmethod
    def get_c(self):
        """Return number of classes in a dataset."""
        raise NotImplementedError

    @abstractmethod
    def get_sz(self):
        """Return maximum size of an image in a dataset."""
        raise NotImplementedError

    @abstractmethod
    def get_x(self, i):
        """Return i-th example (image, wav, etc)."""
        raise NotImplementedError

    @abstractmethod
    def get_y(self, i):
        """Return i-th label."""
        raise NotImplementedError

    @property
    def is_multi(self):
        """Returns true if this data set contains multiple labels per sample."""
        return False

    @property
    def is_reg(self):
        """True if the data set is used to train regression models."""
        return False


def open_image(fn):
    """ Opens an image using OpenCV given the file path.

    Arguments:
        fn: the file path of the image

    Returns:
        The image in RGB format as numpy array of floats normalized to range between 0.0 - 1.0
    """

    flags = cv2.IMREAD_UNCHANGED + cv2.IMREAD_ANYDEPTH + cv2.IMREAD_ANYCOLOR
    if not os.path.exists(fn):
        raise OSError('No such file or directory: {}'.format(fn))
    elif os.path.isdir(fn):
        raise OSError('Is a directory: {}'.format(fn))
    else:
        # res = np.array(Image.open(fn), dtype=np.float32)/255
        # if len(res.shape)==2: res = np.repeat(res[...,None],3,2)
        # return res
        try:
            # (!) modified to accomodate .tif files and use skimage.external.tifffile.imread as channel-number agnostic importer.
            # (!) np.moveaxis used to ensure correct array shape.

            if str(fn).lower().endswith(('.tif', '.tiff', '.tifff')):
                im = tifffile.imread(str(fn)).astype(np.float32) / 65535  # (!) for 16-bit images
                im = np.moveaxis(im, 0, -1) # converting (c,w,h) to (w,h,c)
            else:
                im = cv2.imread(str(fn), flags).astype(np.float32) / 255
                im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
            if im is None: raise OSError(f'File not recognized by io.imread: {fn}')
            return im
        except Exception as e:
            raise OSError('Error handling image at: {}'.format(fn)) from e


class FilesDataset(BaseDataset):
    def __init__(self, fnames, transform, path):
        self.path, self.fnames = path, fnames
        super().__init__(transform)

    def get_sz(self):
        return self.transform.sz

    def get_x(self, i):
        return open_image(os.path.join(self.path, self.fnames[i]))

    def get_n(self):
        return len(self.fnames)

    def resize_imgs(self, targ, new_path):
        dest = resize_imgs(self.fnames, targ, self.path,
                           new_path)  # (!) THIS calls resize_image which uses mode=RGB -> Issues
        return self.__class__(self.fnames, self.y, self.transform, dest)

    def denorm(self, arr, y=None, src_idx=None): # (!) src_idx
        """Reverse the normalization done to a batch of images.

        Arguments:
            arr: of shape/size (N,3,sz,sz)
        """
        if type(arr) is not np.ndarray: arr = to_np(arr)


        if len(arr.shape) == 3: arr = arr[None]
        return self.transform.denorm(np.rollaxis(arr, 1, 4), y, src_idx)    # (!) Get's called in plt.imshow.(data.trn_ds.denorm(x)[0]) which delegates to tranforms.denormalize through tfms_from_stats. Makes indexing confusing!
                                                                            # (!) src_idx

class FilesArrayDataset(FilesDataset):
    def __init__(self, fnames, y, transform, src_idx ,path): #(!) src_idx
        self.y = y
        self.src_idx = src_idx #(!) src_idx
        assert (len(fnames) == len(y))
        super().__init__(fnames, transform, path)

    def get_y(self, i): return self.y[i]

    def get_src_idx(self, i): return self.src_idx[i] if self.src_idx is not None else None #(!) src_idx get method

    def get_c(self):
        return self.y.shape[1] if len(self.y.shape) > 1 else 0


class FilesIndexArrayDataset(FilesArrayDataset):
    def get_c(self): return int(self.y.max()) + 1


class FilesNhotArrayDataset(FilesArrayDataset):
    @property
    def is_multi(self): return True


class FilesIndexArrayRegressionDataset(FilesArrayDataset):
    def is_reg(self): return True


class ArraysDataset(BaseDataset):
    def __init__(self, x, y, transform, src_idx):
        self.x, self.y = x, y
        self.src_idx = src_idx #(!) src_idx
        assert (len(x) == len(y))
        super().__init__(transform)

    def get_src_idx(self, i): return self.src_idx[i] if self.src_idx is not None else None #(!) src_idx get method

    def get_x(self, i): return self.x[i]

    def get_y(self, i): return self.y[i]

    def get_n(self): return len(self.y)

    def get_sz(self): return self.x.shape[1]


class ArraysIndexDataset(ArraysDataset):
    def get_c(self): return int(self.y.max()) + 1

    def get_y(self, i): return self.y[i]


class ArraysNhotDataset(ArraysDataset):
    def get_c(self): return self.y.shape[1]

    @property
    def is_multi(self): return True


class ModelData():
    def __init__(self, path, trn_dl, val_dl, test_dl=None):
        self.path, self.trn_dl, self.val_dl, self.test_dl = path, trn_dl, val_dl, test_dl

    @classmethod # (!!) Sultan, did you write this? Not used atm?
    def from_dls(cls, path, trn_dl, val_dl, test_dl=None):
        # trn_dl,val_dl = DataLoader(trn_dl),DataLoader(val_dl)
        # if test_dl: test_dl = DataLoader(test_dl)
        return cls(path, trn_dl, val_dl, test_dl)

    @property
    def is_reg(self): return self.trn_ds.is_reg

    @property
    def is_multi(self): return self.trn_ds.is_multi

    @property
    def trn_ds(self): return self.trn_dl.dataset

    @property
    def val_ds(self): return self.val_dl.dataset

    @property
    def test_ds(self): return self.test_dl.dataset

    @property
    def trn_y(self): return self.trn_ds.y

    @property
    def val_y(self): return self.val_ds.y


class ImageData(ModelData):
    def __init__(self, path, datasets, bs, num_workers, classes, balance=None): # (!) balance
        trn_ds, val_ds, fix_ds, aug_ds, test_ds, test_aug_ds = datasets
        self.path, self.bs, self.num_workers, self.classes = path, bs, num_workers, classes
        self.trn_dl, self.val_dl, self.fix_dl, self.aug_dl, self.test_dl, self.test_aug_dl = [
            self.get_dl(ds, shuf, weights) for ds, shuf, weights in [ # (!) weights
                (trn_ds, True, balance), (val_ds, False, None), (fix_ds, False, None), (aug_ds, False,None),
                (test_ds, False, None), (test_aug_ds, False, None)
            ]
        ]

    def get_dl(self, ds, shuffle, weights):
        if ds is None: return None
        return DataLoader(ds, batch_size=self.bs, shuffle=shuffle, weights=weights,
                          num_workers=self.num_workers, pin_memory=False)

    @property
    def sz(self):
        return self.trn_ds.sz

    @property
    def c(self):
        return self.trn_ds.c

    def resized(self, dl, targ, new_path):
        return dl.dataset.resize_imgs(targ, new_path) if dl else None

    def resize(self, targ_sz, new_path='tmp'):
        new_ds = []
        dls = [self.trn_dl, self.val_dl, self.fix_dl, self.aug_dl]
        if self.test_dl:
            dls += [self.test_dl, self.test_aug_dl]
        else:
            dls += [None, None]
        t = tqdm_notebook(dls)
        for dl in t: new_ds.append(self.resized(dl, targ_sz, new_path))
        t.close()
        return self.__class__(new_ds[0].path, new_ds, self.bs, self.num_workers, self.classes)

    @staticmethod
    def get_ds(fn, trn, val, tfms, test=None, **kwargs):

        
        if len(trn) == 5:
            res = [           
                fn(trn[0], trn[1], tfms[0], trn[3], **kwargs),  # train
                fn(val[0], val[1], tfms[1], val[3], **kwargs),  # val
                fn(trn[0], trn[1], tfms[1], trn[3], **kwargs),  # fix
                fn(val[0], val[1], tfms[0], val[3], **kwargs)  # aug
            ]

        else:
            res = [
                fn(trn[0], trn[1], tfms[0], None, **kwargs),  # train
                fn(val[0], val[1], tfms[1], None, **kwargs),  # val
                fn(trn[0], trn[1], tfms[1], None, **kwargs),  # fix
                fn(val[0], val[1], tfms[0], None, **kwargs)  # aug
            ]

        # res[0].idx_to_class = trn[2] #(!) What does this do?!

        if test is not None:
            # if isinstance(test, tuple):
            #     test_lbls = test[1]
            #     test = test[0]
            #     test_src_idx = test[3]
            #     # print('Tuple')
            # else:
            #     test_lbls = np.zeros((len(test), 1))
            #     # print('Not_tuple')

            # res += [
            #     fn(test, test_lbls, tfms[2], test_src_idx, **kwargs),  # test (!) 1 -> 2
            #     fn(test, test_lbls, tfms[0], test_src_idx, **kwargs)  # test_aug
            # ]
            
            if isinstance(test, tuple):
                res += [
                    fn(test[0], test[1], tfms[2], test[3], **kwargs),  # test (!) 1 -> 2
                    fn(test[0], test[1], tfms[0], test[3], **kwargs)  # test_aug
                ]
            else:
                test_lbls = np.zeros((len(test), 1))
                res += [
                    fn(test, test_lbls, tfms[2], **kwargs),  # test (!) 1 -> 2
                    fn(test, test_lbls, tfms[0], **kwargs)  # test_aug
                ]

        else:
            res += [None, None]
            # print('Test is None')
        return res


class ImageClassifierData(ImageData):
    @classmethod
    def from_arrays(cls, path, trn, val, bs=64, tfms=(None, None), classes=None, num_workers=4, test=None):
        """ Read in images and their labels given as numpy arrays

        Arguments:
            path: a root path of the data (used for storing trained models, precomputed values, etc)
            trn: a tuple of training data matrix and target label/classification array (e.g. `trn=(x,y)` where `x` has the
                shape of `(5000, 784)` and `y` has the shape of `(5000,)`)
            val: a tuple of validation data matrix and target label/classification array.
            bs: batch size
            tfms: transformations (for data augmentations). e.g. output of `tfms_from_model`
            classes: a list of all labels/classifications
            num_workers: a number of workers
            test: a matrix of test data (the shape should match `trn[0]`)

        Returns:
            ImageClassifierData
        """
        datasets = cls.get_ds(ArraysIndexDataset, trn, val, tfms, test=test)
        return cls(path, datasets, bs, num_workers, classes=classes)

    @classmethod
    def prepare_from_path(cls, path, bs=64, trn_name='train', val_name='valid', test_name=None, test_with_labels=False,
                          num_workers=8, balance=False):
        """ Read in images and their labels given as sub-folder names

        Arguments:
            path: a root path of the data (used for storing trained models, precomputed values, etc)
            bs: batch size
            tfms: transformations (for data augmentations). e.g. output of `tfms_from_model`
            trn_name: a name of the folder that contains training images.
            val_name:  a name of the folder that contains validation images.
            test_name:  a name of the folder that contains test images.
            num_workers: number of workers

        Returns:
            ImageClassifierData
        """
        lbl2index = {}  # gets populated in the folder_source calls
        test_lbl2index = {}

        trn, val = [folder_source(path, o, lbl2index) for o in (trn_name, val_name)]
        if balance:
            weights = compute_adjusted_weights(trn)
        else:
            weights = None

        if test_name:
            test = folder_source(path, test_name, test_lbl2index) if test_with_labels else read_dir(path, test_name)
        else:
            test = None
        def create(tfms):
            datasets = cls.get_ds(FilesIndexArrayDataset, trn, val, tfms, path=path, test=test)
            return cls(path, datasets, bs, num_workers, classes=trn[2], balance=weights)

        return create, lbl2index, test_lbl2index

    @classmethod
    def from_csv(cls, path, folder, csv_fname, bs=64, tfms=(None, None),
                 val_idxs=None, suffix='', test_name=None, continuous=False, skip_header=True, num_workers=8):
        """ Read in images and their labels given as a CSV file.

        This method should be used when training image labels are given in an CSV file as opposed to
        sub-directories with label names.

        Arguments:
            path: a root path of the data (used for storing trained models, precomputed values, etc)
            folder: a name of the folder in which training images are contained.
            csv_fname: a name of the CSV file which contains target labels.
            bs: batch size
            tfms: transformations (for data augmentations). e.g. output of `tfms_from_model`
            val_idxs: index of images to be used for validation. e.g. output of `get_cv_idxs`.
                If None, default arguments to get_cv_idxs are used.
            suffix: suffix to add to image names in CSV file (sometimes CSV only contains the file name without file
                    extension e.g. '.jpg' - in which case, you can set suffix as '.jpg')
            test_name: a name of the folder which contains test images.
            continuous: TODO
            skip_header: skip the first row of the CSV file.
            num_workers: number of workers

        Returns:
            ImageClassifierData
        """
        assert not (tfms[0] is None or tfms[
            1] is None), "please provide transformations for your train and validation sets"
        assert not (os.path.isabs(folder)), "folder needs to be a relative path"
        fnames, y, classes = csv_source(folder, csv_fname, skip_header, suffix, continuous=continuous)
        return cls.from_names_and_array(path, fnames, y, classes, val_idxs, test_name,
                                        num_workers=num_workers, suffix=suffix, tfms=tfms, bs=bs, continuous=continuous)

    @classmethod
    def from_names_and_array(cls, path, fnames, y, classes, val_idxs=None, test_name=None,
                             num_workers=8, suffix='', tfms=(None, None), bs=64, continuous=False):
        val_idxs = get_cv_idxs(len(fnames)) if val_idxs is None else val_idxs
        ((val_fnames, trn_fnames), (val_y, trn_y)) = split_by_idx(val_idxs, np.array(fnames), y)

        test_fnames = read_dir(path, test_name) if test_name else None
        if continuous:
            f = FilesIndexArrayRegressionDataset
        else:
            f = FilesIndexArrayDataset if len(trn_y.shape) == 1 else FilesNhotArrayDataset
        datasets = cls.get_ds(f, (trn_fnames, trn_y), (val_fnames, val_y), tfms,
                              path=path, test=test_fnames)
        return cls(path, datasets, bs, num_workers, classes=classes)


def split_by_idx(idxs, *a):
    """
    Split each array passed as *a, to a pair of arrays like this (elements selected by idxs,  the remaining elements)
    This can be used to split multiple arrays containing training data to validation and training set.

    :param idxs [int]: list of indexes selected
    :param a list: list of np.array, each array should have same amount of elements in the first dimension
    :return: list of tuples, each containing a split of corresponding array from *a.
            First element of each tuple is an array composed from elements selected by idxs,
            second element is an array of remaining elements.
    """
    mask = np.zeros(len(a[0]), dtype=bool)
    mask[np.array(idxs)] = True
    return [(o[mask], o[~mask]) for o in a]


def compute_default_weights(dataset):
    """
    :param dataset: dataset[0]: samples and names e.g. generic_filename; dataset[1] labels e.g. 0 or 1
    :return: set of weights/probabilities for each sample; represents how often it is picked
    """
    weights = np.zeros(len(dataset[1]))
    labels = list(set(dataset[1]))
    occurrences = np.bincount(dataset[1])
    probs = [100 * count/sum(occurrences) for count in occurrences]

    for idx, label in enumerate(labels):
        weights[dataset[1] == label] = probs[idx] / occurrences[idx]

    return weights


def compute_adjusted_weights(dataset):
    """
    :param dataset: dataset[0]: samples and names e.g. generic_filename; dataset[1] labels e.g. 0 or 1
    :return: set of weights/probabilities for each sample; represents how often it is picked
    """
    weights = np.zeros(len(dataset[1]))
    labels = list(set(dataset[1]))
    occurrences = np.bincount(dataset[1])
    probs = [100 * count/sum(occurrences) for count in occurrences]

    for idx, label in enumerate(labels):
        weights[dataset[1] == label] = probs[idx] / occurrences[idx]
    desired = 100 / len(labels) # desired probability per class

    for idx, prob in enumerate(probs):
        delta = desired - prob # unlikely to be 0
        correction = delta / occurrences[idx]
        weights[dataset[1] == labels[idx]] += correction

    return weights


def balance_ds(dataset):
    """
    :param dataset: 0: train filenames, 1: labels as indexes, classes
    :return:
    """
    counter = Counter(dataset[1]) # count how many of each label in the dataset
    print("BEFORE: ", counter)

    # for efficiency purposes
    dataset = list(dataset)
    dataset[1] = list(dataset[1])

    max_label, max_count = counter.most_common(1)[0]
    for label in set(dataset[1]):
        if label != max_label:
            delta = max_count - counter[label]
            additions = np.random.choice(dataset[0], delta, replace=False)
            labels = [label] * delta
            dataset[0].extend(additions)
            dataset[1].extend(labels)

    # conversion back to the old types
    dataset[1] = np.array(dataset[1])
    dataset = tuple(dataset)

    counter = Counter(dataset[1])  # count how many of each label in the dataset after the adjustment
    print("AFTER: ", counter)
    return dataset